def histogram_bins(lst):
    bins = {}

    for num in lst:
        # Determine bin range
        lower = (num // 10) * 10 + 1
        upper = lower + 9

        key = f"{lower}-{upper}"

        bins[key] = bins.get(key, 0) + 1

    # Sort bins by range
    sorted_bins = dict(sorted(bins.items(), key=lambda x: int(x[0].split('-')[0])))

    return sorted_bins


# Sample Input
lst = [13,42,15,37,22,39,41,50]

print(histogram_bins(lst))