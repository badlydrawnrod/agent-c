def fib(n: int) -> int:
    """
    Return the nth Fibonacci number.
    """
    if n < 0:
        raise ValueError("n must be non-negative")

    def _fib_pair(k: int):
        if k == 0:
            return (0, 1)  # (F(k), F(k+1))
        a, b = _fib_pair(k >> 1)
        c = a * ((b << 1) - a)  # F(2k)
        d = a * a + b * b  # F(2k+1)
        return (c, d) if k & 1 == 0 else (d, c + d)

    return _fib_pair(n)[0]


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python fib.py <n>")
        sys.exit(1)

    try:
        n = int(sys.argv[1])
        result = fib(n)
        print(f"fib({n}) = {result}")
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
