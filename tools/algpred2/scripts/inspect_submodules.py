import algpred2
import pkgutil

print("algpred2 import ok")
print("Package path:", algpred2.__path__)
print("Submodules:")
print([m.name for m in pkgutil.iter_modules(algpred2.__path__)])