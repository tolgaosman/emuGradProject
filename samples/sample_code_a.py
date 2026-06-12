"""Sample A: compute basic statistics for a list of numbers."""


def compute_average(numbers):
    total = 0
    for value in numbers:
        total = total + value
    return total / len(numbers)


def compute_maximum(numbers):
    largest = numbers[0]
    for value in numbers:
        if value > largest:
            largest = value
    return largest


def main():
    data = [4, 8, 15, 16, 23, 42]
    print("Average:", compute_average(data))
    print("Maximum:", compute_maximum(data))


if __name__ == "__main__":
    main()
