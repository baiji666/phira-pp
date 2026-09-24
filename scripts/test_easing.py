"""Verify easing functions: f(0)=0 and f(1)=1 for every RPE easingType."""

from phira_pp.easing import EASINGS, get

TOL = 1e-9


def main():
    failures = []
    for i, fn in enumerate(EASINGS, start=1):
        if abs(fn(0.0) - 0.0) > TOL:
            failures.append((i, "f(0)", fn(0.0)))
        if abs(fn(1.0) - 1.0) > TOL:
            failures.append((i, "f(1)", fn(1.0)))
        if not -3.0 <= fn(0.5) <= 4.0:
            failures.append((i, "f(0.5)", fn(0.5)))
    print(f"checked {len(EASINGS)} easings")
    if failures:
        for f in failures:
            print("  FAIL", f)
    else:
        print("all endpoints OK")
    # clamping behaviour
    assert get(0) is EASINGS[0]
    assert get(1) is EASINGS[0]
    assert get(29) is EASINGS[28]
    assert get(99) is EASINGS[28]
    assert get("x") is EASINGS[0]
    print("clamping OK")


if __name__ == "__main__":
    main()
