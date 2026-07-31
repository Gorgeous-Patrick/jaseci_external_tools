"""Entry point for info."""
import sys, sysconfig;

with entry {
    print("Hello from info!");
    print(f"Embedded Python version: {sys.version}"); 
    print(f"GIL enabled: {sys._is_gil_enabled()}");
}
