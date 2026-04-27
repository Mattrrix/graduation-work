import random


def gen_inn(rng: random.Random, length: int = 10) -> str:
    if length not in (10, 12):
        raise ValueError("INN length must be 10 or 12")
    if length == 10:
        digits = [rng.randint(0, 9) for _ in range(9)]
        coef = [2, 4, 10, 3, 5, 9, 4, 6, 8]
        check = sum(d * c for d, c in zip(digits, coef)) % 11 % 10
        digits.append(check)
    else:
        digits = [rng.randint(0, 9) for _ in range(10)]
        coef1 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        coef2 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        c1 = sum(digits[i] * coef1[i] for i in range(10)) % 11 % 10
        digits.append(c1)
        c2 = sum(digits[i] * coef2[i] for i in range(11)) % 11 % 10
        digits.append(c2)
    return "".join(map(str, digits))


def gen_kpp(rng: random.Random) -> str:
    return "".join(str(rng.randint(0, 9)) for _ in range(4)) + "01" + "".join(str(rng.randint(0, 9)) for _ in range(3))
