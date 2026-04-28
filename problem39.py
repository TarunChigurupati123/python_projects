import math

def nearest_point(points, query):
    closest = None
    min_dist = float('inf')

    for p in points:
        # Euclidean distance
        dist = math.sqrt((p[0] - query[0])**2 + (p[1] - query[1])**2)

        if dist < min_dist:
            min_dist = dist
            closest = p

    return closest


# Sample Input
points = [(1,1), (2,2), (3,3), (4,4)]
query = (0,0)

result = nearest_point(points, query)
print(f"Nearest to {query} is {result}")