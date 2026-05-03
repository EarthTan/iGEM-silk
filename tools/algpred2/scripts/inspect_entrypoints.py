import importlib.metadata as md

dist = md.distribution("algpred2")
print("Entry points:")
for ep in dist.entry_points:
    print(ep)