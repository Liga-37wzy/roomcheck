import json
import io
from pathlib import Path
import random
import subprocess
import sys
import unittest
from unittest.mock import patch

from roomcheck.core import ModelError, check, parse_model
from roomcheck.__main__ import load_model, unique_keys

ROOT = Path(__file__).resolve().parents[1]


def example(name):
    return load_model(ROOT / "examples" / (name + ".json"))


def small(actions, initial=None, must_solve=None):
    return {"version": 1, "facts": ["key", "clue", "win"], "initial": initial or [],
            "goals": ["win"], "actions": actions, "must_solve": must_solve or []}


class CheckerTests(unittest.TestCase):
    def test_physical_parallel_flow(self):
        result = check(example("physical"))
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["all_states_can_win"])
        self.assertEqual(len(result["solution"]), 4)

    def test_digital_or_alternatives(self):
        result = check(example("digital"))
        self.assertEqual(result["status"], "ok")
        self.assertEqual(len(result["solution"]), 3)

    def test_consumption_softlock(self):
        result = check(example("softlock"))
        self.assertTrue(result["solvable"])
        issue = next(i for i in result["issues"] if i["code"] == "SOFTLOCK")
        self.assertEqual(issue["trace"], ["play_radio"])
        self.assertFalse(result["all_states_can_win"])

    def test_circular_dependency_blocks_goal(self):
        result = check(example("circular"))
        self.assertFalse(result["solvable"])
        self.assertIn("NO_SOLUTION", [i["code"] for i in result["issues"]])

    def test_bypass_has_witness(self):
        result = check(example("bypass"))
        issue = next(i for i in result["issues"] if i["code"] == "REQUIRED_BYPASS")
        self.assertEqual(issue["trace"], ["open_exit"])
        self.assertEqual(issue["skipped"], ["decode"])

    def test_budget_is_unknown_not_success(self):
        result = check(example("physical"), 1)
        self.assertEqual(result["status"], "inconclusive")
        self.assertIsNone(result["solvable"])
        self.assertIsNone(result["all_states_can_win"])
        self.assertEqual([i["code"] for i in result["issues"]], ["SEARCH_LIMIT"])

    def test_softlock_detected_before_terminal_dead_end(self):
        data = small([{"id": "spend", "consumes": ["key"], "produces": ["clue"]},
                      {"id": "look", "requires_all": ["clue"], "produces": []},
                      {"id": "escape", "consumes": ["key"], "produces": ["win"]}], ["key"])
        result = check(parse_model(data))
        trapped = next(i for i in result["issues"] if i["code"] == "SOFTLOCK")
        terminal = next(i for i in result["issues"] if i["code"] == "DEAD_END")
        self.assertEqual(trapped["trace"], ["spend"])
        self.assertEqual(terminal["trace"], ["spend", "look"])

    def test_found_win_does_not_imply_safety_after_cutoff(self):
        data = small([{"id": "escape", "produces": ["win"]},
                      {"id": "key", "produces": ["key"]},
                      {"id": "clue", "produces": ["clue"]}])
        result = check(parse_model(data), 4)
        self.assertTrue(result["solvable"])
        self.assertFalse(result["complete"])
        self.assertIsNone(result["all_states_can_win"])

    def test_initial_victory_empty_trace(self):
        data = small([], ["win"])
        result = check(parse_model(data))
        self.assertEqual(result["solution"], [])
        self.assertTrue(result["all_states_can_win"])

    def test_win_stops_actions(self):
        data = small([{"id": "lose", "consumes": ["win"], "produces": []}], ["win"])
        result = check(parse_model(data))
        self.assertEqual(result["states"], 1)
        self.assertEqual(result["status"], "ok")

    def test_consumes_requires_presence(self):
        result = check(parse_model(small([{"id": "escape", "consumes": ["key"], "produces": ["win"]}])))
        self.assertFalse(result["solvable"])

    def test_and_or_both_apply(self):
        data = small([{"id": "escape", "requires_all": ["key"], "requires_any": ["clue"],
                       "produces": ["win"]}], ["key"])
        self.assertFalse(check(parse_model(data))["solvable"])
        data["initial"].append("clue")
        self.assertTrue(check(parse_model(data))["solvable"])

    def test_seeded_cycle_is_not_automatically_error(self):
        data = small([{"id": "a", "requires_all": ["key"], "produces": ["clue"]},
                      {"id": "b", "requires_all": ["clue"], "produces": ["key", "win"]}], ["key"])
        self.assertEqual(check(parse_model(data))["status"], "ok")

    def test_recovery_path_prevents_false_softlock(self):
        data = small([{"id": "spend", "consumes": ["key"], "produces": ["clue"]},
                      {"id": "recover", "requires_all": ["clue"], "produces": ["key"]},
                      {"id": "escape", "consumes": ["key"], "produces": ["win"]}], ["key"])
        self.assertTrue(check(parse_model(data))["all_states_can_win"])

    def test_duplicate_or_unknown_fields_rejected(self):
        with self.assertRaises(ModelError):
            unique_keys([("version", 1), ("version", 1)])
        data = small([])
        data["action"] = []
        with self.assertRaises(ModelError):
            parse_model(data)

    def test_invalid_models(self):
        valid = small([{"id": "escape", "produces": ["win"]}])
        variants = [{**valid, "version": True}, {**valid, "goals": []},
                    {**valid, "initial": ["missing"]}, {**valid, "facts": ["win", "win"]},
                    {**valid, "actions": valid["actions"] * 2}, {**valid, "must_solve": ["missing"]},
                    {**valid, "actions": [{"id": "x", "produces": ["win"], "consumes": ["win"]}]},
                    {**valid, "actions": [{"id": "x", "produces": "win"}]},
                    {**valid, "actions": [{"id": "x", "produces": [], "repeatable": True}]}]
        for data in variants:
            with self.subTest(data=data), self.assertRaises(ModelError):
                parse_model(data)

    def test_limits_validated(self):
        for limit in [0, -1, True, 100001]:
            with self.subTest(limit=limit), self.assertRaises(ModelError):
                check(example("physical"), limit)

    def test_random_models_against_independent_trace_enumeration(self):
        # Exhaustive action-sequence tree is slower but independent of BFS merging
        # and reverse reachability; tiny random models make it a useful oracle.
        rng = random.Random(42)
        for case in range(100):
            facts = ["key", "clue", "win"]
            subset = lambda: [f for f in facts if rng.random() < .3]
            actions = []
            for i in range(4):
                consumes = subset()
                actions.append({"id": f"a{i}", "requires_all": subset(), "requires_any": subset(),
                                "consumes": consumes, "produces": [f for f in subset() if f not in consumes]})
            data = small(actions, subset(), ["a0"])

            def walk(inventory, done):
                if "win" in inventory:
                    return True, True, "a0" not in done
                children = []
                for a in actions:
                    if (a["id"] not in done and set(a["requires_all"]) <= inventory
                            and set(a["consumes"]) <= inventory
                            and (not a["requires_any"] or set(a["requires_any"]) & inventory)):
                        children.append(walk((inventory - set(a["consumes"])) | set(a["produces"]),
                                             done | {a["id"]}))
                return (any(x[0] for x in children), bool(children) and all(x[1] for x in children),
                        any(x[2] for x in children))

            expected = walk(set(data["initial"]), set())
            actual = check(parse_model(data))
            with self.subTest(case=case):
                self.assertEqual(actual["solvable"], expected[0])
                self.assertEqual(actual["all_states_can_win"], expected[1])
                self.assertEqual(any(i["code"] == "REQUIRED_BYPASS" for i in actual["issues"]), expected[2])


class CommandTests(unittest.TestCase):
    def test_loader_rejects_bad_bytes_and_duplicate_fields(self):
        for raw in [b'\xff', b'{', b'{"version":1,"version":1}', b' ' * 1_048_577]:
            with self.subTest(raw=raw[:40]):
                with patch.object(Path, "open", return_value=io.BytesIO(raw)):
                    with self.assertRaises((ValueError, UnicodeError)):
                        load_model("unused.json")

    def test_loader_accepts_utf8_bom(self):
        raw = b'\xef\xbb\xbf' + json.dumps(small([], ["win"])).encode("utf-8")
        with patch.object(Path, "open", return_value=io.BytesIO(raw)):
            self.assertTrue(check(load_model("unused.json"))["solvable"])

    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-m", "roomcheck", *args], cwd=ROOT,
                              capture_output=True, text=True, encoding="utf-8")

    def test_cli_exit_codes_and_json(self):
        for filename, extra, code in [("physical", [], 0), ("softlock", [], 1),
                                      ("physical", ["--max-states", "1"], 3),
                                      ("does_not_exist", [], 2)]:
            with self.subTest(filename=filename, extra=extra):
                result = self.run_cli(f"examples/{filename}.json", "--json", *extra)
                self.assertEqual(result.returncode, code, result.stderr)
                self.assertIn("status", json.loads(result.stdout))

    def test_text_output(self):
        result = self.run_cli("examples/softlock.json")
        self.assertEqual(result.returncode, 1)
        self.assertIn("play_radio", result.stdout)


if __name__ == "__main__":
    unittest.main()
