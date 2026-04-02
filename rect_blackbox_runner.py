import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple


@dataclass
class Box:
    x: float
    y: float
    width: float
    height: float


def is_valid_box(box: Box) -> bool:
    ints = [box.x, box.y, box.width, box.height]
    return all(isinstance(v, int) or (isinstance(v, float) and float(v).is_integer()) for v in ints) and box.x >= 0 and box.y >= 0 and box.width >= 1 and box.height >= 1


def do_both_ways(box1: Box, box2: Box, func: Callable[[Box, Box], bool]) -> bool:
    return func(box1, box2) or func(box2, box1)


def alg_a(box1: Box, box2: Box) -> bool:
    def inner(b1: Box, b2: Box) -> bool:
        if (((b1.y >= b2.y and b1.x >= b2.x) and (b1.y < (b2.y + b2.height) and b1.x < (b2.x + b2.width))) or
            ((b1.y >= b2.y and b1.x + b1.width <= b2.x + b2.width) and (b1.y < (b2.y + b2.height) and b1.x + b1.width > b2.x))):
            return True
        return False
    return do_both_ways(box1, box2, inner)


def alg_b(box2: Box, box1: Box) -> bool:
    # faithful transcription of repository code, minus the stray syntax typo in the published file
    if (((box1.y >= box2.y and box1.x >= box2.x) and (box1.y < (box2.y + box2.height) and box1.x < (box2.x + box2.width))) or
        ((box1.y >= box2.y and box1.x + box1.width <= box2.x + box1.width) and (box1.y < (box2.y + box2.height) and box1.x + box1.width < box2.x)) or
        ((box1.y < box2.y and box1.x > box2.x) and ((box1.y + box1.height) > (box2.y + box2.height) and (box1.x + box1.width) < (box2.x + box2.width)))):
        return True
    return False


def alg_c(box1: Box, box2: Box) -> bool:
    return (
        box1.x <= (box2.x + box2.width)
        and (box1.x + box1.width) >= box2.x
        and box1.y <= (box2.y + box2.height)
        and (box1.y + box1.height) >= box2.y
    )


def alg_d(box1: Box, box2: Box) -> bool:
    def inner(b1: Box, b2: Box) -> bool:
        if ((b1.x > b2.x and b1.x < (b2.x + b2.width)) or
            (b1.y > b2.y and b1.y < (b2.y + b2.height)) or
            ((b1.x + b1.width) > b2.x and (b1.x + b1.width) < (b2.x + b2.width)) or
            ((b1.y + b1.height) > b2.y and (b1.y + b1.height) < (b2.y + b2.height))):
            return True
        return False
    return do_both_ways(box1, box2, inner)


def alg_e(box1: Box, box2: Box) -> bool:
    return (
        box1.x < (box2.x + box2.width)
        and (box1.x + box1.width) > box2.x
        and box1.y < (box2.y + box2.height)
        and (box1.y + box1.height) > box2.y
    )


def alg_f(box1: Box, box2: Box) -> bool:
    def inner(b1: Box, b2: Box) -> bool:
        if (((b1.y >= b2.y and b1.x >= b2.x) and (b1.y < (b2.y + b2.height) and b1.x < (b2.x + b2.width))) or
            ((b1.y >= b2.y and b1.x + b1.width <= b2.x + b2.width) and (b1.y < (b2.y + b2.height) and b1.x + b1.width > b2.x)) or
            ((b1.y < b2.y and b1.x > b2.x) and ((b1.y + b1.height) > (b2.y + b2.height) and (b1.x + b1.width) < (b2.x + b2.width)))):
            return True
        return False
    return do_both_ways(box1, box2, inner)


ALGORITHMS: Dict[str, Callable[[Box, Box], bool]] = {
    "a": alg_a,
    "b": alg_b,
    "c": alg_c,
    "d": alg_d,
    "e": alg_e,
    "f": alg_f,
}


def load_cases(path: Path) -> List[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_case(case: dict) -> Tuple[Optional[str], Dict[str, str]]:
    box1 = Box(**case["box1"])
    box2 = Box(**case["box2"])
    expected = case["expected"]

    if expected is None:
        valid = is_valid_box(box1) and is_valid_box(box2)
        return ("INVALID_EXPECTED", {name: ("FAIL" if valid else "PASS") for name in ALGORITHMS})

    outcomes = {}
    for name, fn in ALGORITHMS.items():
        actual = fn(box1, box2)
        outcomes[name] = "PASS" if actual == expected else f"FAIL(actual={actual})"
    return (None, outcomes)


def summarize(results: List[Tuple[dict, Optional[str], Dict[str, str]]]) -> str:
    bug_hits = {name: [] for name in ALGORITHMS}
    for case, _, outcome in results:
        for name, status in outcome.items():
            if status.startswith("FAIL"):
                bug_hits[name].append(case["id"])

    lines = ["\n=== 缺陷汇总 ==="]
    for name in ALGORITHMS:
        ids = bug_hits[name]
        if ids:
            lines.append(f"算法{name}: 存在疑似BUG，被用例 {', '.join(ids)} 检出")
        else:
            lines.append(f"算法{name}: 在当前测试集下未检出缺陷")
    return "\n".join(lines)


def main() -> None:
    base = Path(__file__).resolve().parent
    cases = load_cases(base / "test_cases.json")
    results = []

    print("=== 四边形覆盖问题黑盒测试 ===")
    for case in cases:
        flag, outcome = evaluate_case(case)
        results.append((case, flag, outcome))
        print(f"\n[{case['id']}] {case['name']} | 方法={case['method']} | 目的={case['purpose']}")
        if case["expected"] is None:
            print("  预期: 非法输入应被拒绝/标记无效")
        else:
            print(f"  预期输出: {case['expected']}")
        for name in ALGORITHMS:
            print(f"    算法{name}: {outcome[name]}")

    print(summarize(results))


if __name__ == "__main__":
    main()
