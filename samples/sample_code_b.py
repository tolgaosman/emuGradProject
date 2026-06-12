"""Sample B: compute basic statistics (renamed variables/functions)."""


def mean_of(items):
    running = 0
    for element in items:
        running = running + element
    return running / len(items)


def peak_of(items):
    biggest = items[0]
    for element in items:
        if element > biggest:
            biggest = element
    return biggest


def run():
    series = [4, 8, 15, 16, 23, 42]
    print("Average:", mean_of(series))
    print("Maximum:", peak_of(series))


if __name__ == "__main__":
    run()
