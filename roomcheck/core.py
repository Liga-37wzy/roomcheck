"""Small explicit-state checker. No network, third-party packages or execution of input."""

from collections import deque
from dataclasses import dataclass
import re


class ModelError(ValueError):
    """The supplied model is invalid or outside the supported scope."""


@dataclass(frozen=True)
class Action:
    id: str
    label: str
    requires_all: frozenset
    requires_any: frozenset
    consumes: frozenset
    produces: frozenset


@dataclass(frozen=True)
class Model:
    title: str
    initial: frozenset
    goals: frozenset
    actions: tuple
    must_solve: frozenset


def _object(value, allowed, required, path):
    if not isinstance(value, dict):
        raise ModelError(f"{path}: expected an object")
    unknown, missing = set(value) - allowed, required - set(value)
    if unknown or missing:
        raise ModelError(f"{path}: unknown fields {sorted(unknown)}; missing fields {sorted(missing)}")


def _ids(value, path):
    if not isinstance(value, list):
        raise ModelError(f"{path}: expected a list of IDs")
    if any(not isinstance(x, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", x) for x in value):
        raise ModelError(f"{path}: IDs must match [a-z][a-z0-9_]{{0,63}}")
    if len(value) != len(set(value)):
        raise ModelError(f"{path}: duplicate IDs")
    return frozenset(value)


def parse_model(data):
    _object(data, {"version", "title", "facts", "initial", "goals", "actions", "must_solve"},
            {"version", "facts", "initial", "goals", "actions"}, "model")
    if type(data["version"]) is not int or data["version"] != 1:
        raise ModelError("version: expected integer 1")
    title = data.get("title", "Untitled room")
    if not isinstance(title, str) or not title.strip() or len(title) > 200:
        raise ModelError("title: expected 1-200 characters")
    facts = _ids(data["facts"], "facts")
    if not 1 <= len(facts) <= 128:
        raise ModelError("facts: expected 1-128 facts")

    def refs(value, path):
        result = _ids(value, path)
        if result - facts:
            raise ModelError(f"{path}: undeclared facts {sorted(result - facts)}")
        return result

    initial, goals = refs(data["initial"], "initial"), refs(data["goals"], "goals")
    if not goals:
        raise ModelError("goals: at least one goal is required")
    raw_actions = data["actions"]
    if not isinstance(raw_actions, list) or len(raw_actions) > 40:
        raise ModelError("actions: expected a list with at most 40 actions")
    actions = []
    for index, raw in enumerate(raw_actions):
        path = f"actions[{index}]"
        _object(raw, {"id", "label", "requires_all", "requires_any", "consumes", "produces"},
                {"id", "produces"}, path)
        _ids([raw["id"]], path + ".id")
        label = raw.get("label", raw["id"])
        if not isinstance(label, str) or not label.strip() or len(label) > 200:
            raise ModelError(f"{path}.label: expected 1-200 characters")
        fields = [refs(raw.get(key, []), path + "." + key)
                  for key in ("requires_all", "requires_any", "consumes", "produces")]
        if fields[2] & fields[3]:
            raise ModelError(f"{path}: consumes and produces must not overlap")
        actions.append(Action(raw["id"], label, *fields))
    action_ids = _ids([a.id for a in actions], "actions IDs")
    must_solve = _ids(data.get("must_solve", []), "must_solve")
    if must_solve - action_ids:
        raise ModelError(f"must_solve: unknown actions {sorted(must_solve - action_ids)}")
    return Model(title, initial, goals, tuple(actions), must_solve)


def check(model, max_states=20000):
    """Enumerate reachable states, then reverse-search all winning states.

    A state contains current facts AND completed one-shot actions. Winning is
    terminal. A full search proves whether every reachable state can still win;
    a bounded search reports unknown, never an unsupported safety claim.
    """
    if type(max_states) is not int or not 1 <= max_states <= 100000:
        raise ModelError("max_states: expected an integer from 1 to 100000")
    start = (model.initial, frozenset())
    parents = {start: None}
    reverse = {start: []}
    queue = deque([start])
    wins, dead, fired = [], [], set()
    complete = True
    transitions = 0
    while queue:
        state = queue.popleft()
        inventory, done = state
        if model.goals <= inventory:
            wins.append(state)
            continue
        enabled = [a for a in model.actions if a.id not in done
                   and a.requires_all <= inventory and a.consumes <= inventory
                   and (not a.requires_any or a.requires_any & inventory)]
        if not enabled:
            dead.append(state)
        for action in enabled:
            nxt = ((inventory - action.consumes) | action.produces, done | {action.id})
            if nxt not in parents:
                if len(parents) >= max_states:
                    complete = False
                    break
                parents[nxt] = (state, action.id)
                reverse[nxt] = []
                queue.append(nxt)
            reverse[nxt].append(state)
            transitions += 1
            fired.add(action.id)
        if not complete:
            break

    def trace(state):
        path = []
        while parents[state] is not None:
            state, action_id = parents[state]
            path.append(action_id)
        return list(reversed(path))

    def witness(state):
        return {"trace": trace(state), "inventory": sorted(state[0]), "completed": sorted(state[1])}

    issues = []
    if not complete:
        issues.append({"code": "SEARCH_LIMIT", "severity": "warning",
                       "message": "State budget reached; absence of problems is not proven. Increase the limit or simplify the model."})
    if complete and not wins:
        issues.append({"code": "NO_SOLUTION", "severity": "error",
                       "message": "No winning path exists in this model."})
    if dead:
        issues.append({"code": "DEAD_END", "severity": "error",
                       "message": "A reachable unfinished state has no enabled actions.",
                       **witness(dead[0])})
    recoverable = set(wins)
    back = deque(wins)
    while back:
        for prev in reverse[back.popleft()]:
            if prev not in recoverable:
                recoverable.add(prev)
                back.append(prev)
    if complete and wins:
        trapped = next((s for s in parents if s not in recoverable), None)
        if trapped is not None:
            issues.append({"code": "SOFTLOCK", "severity": "error",
                           "message": "This choice sequence makes the goal unreachable, although another path can win.",
                           **witness(trapped)})
    bypass = next((s for s in wins if not model.must_solve <= s[1]), None)
    if bypass is not None:
        issues.append({"code": "REQUIRED_BYPASS", "severity": "error",
                       "message": "A winning path skips an action declared mandatory.",
                       "skipped": sorted(model.must_solve - bypass[1]), **witness(bypass)})
    unreachable = sorted(a.id for a in model.actions if a.id not in fired)
    if complete and unreachable:
        issues.append({"code": "UNREACHABLE_ACTION", "severity": "warning",
                       "message": "Actions cannot occur before the game ends; check conditions or remove intentional unused content.",
                       "actions": unreachable})
    errors = any(i["severity"] == "error" for i in issues)
    return {"title": model.title, "complete": complete,
            "status": "issues" if errors else ("ok" if complete else "inconclusive"),
            "states": len(parents), "transitions": transitions,
            "solvable": True if wins else (False if complete else None),
            "all_states_can_win": (len(recoverable) == len(parents)) if complete else None,
            "solution": trace(wins[0]) if wins else None,
            "issues": issues}
