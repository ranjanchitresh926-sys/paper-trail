"""Paper Trail setup check. Run:  python check_setup.py
Prints PASS / WARN / FAIL for everything the project needs, with what to do about each."""
import json, os, platform, shutil, subprocess, sys, urllib.request

rows = []
def add(status, name, detail=""):
    rows.append((status, name, detail))
    print(f"[{status:4}] {name}" + (f"  -  {detail}" if detail else ""))

# Python
v = sys.version_info
add("PASS" if (3, 10) <= v[:2] <= (3, 13) and sys.maxsize > 2**32 else "WARN",
    "Python", f"{platform.python_version()} {'64-bit' if sys.maxsize > 2**32 else '32-bit (need 64-bit)'}; 3.10-3.13 recommended")
add("PASS" if sys.prefix != getattr(sys, 'base_prefix', sys.prefix) else "WARN",
    "Virtual environment", "active" if sys.prefix != getattr(sys, 'base_prefix', sys.prefix) else "not active (recommended: python -m venv .venv)")

# NVIDIA driver / GPU
try:
    out = subprocess.run(["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
                         capture_output=True, text=True, timeout=20).stdout.strip()
    add("PASS" if out else "FAIL", "NVIDIA GPU (nvidia-smi)", out or "no output")
except Exception as e:
    add("FAIL", "NVIDIA GPU (nvidia-smi)", f"not found ({e}); update/install the NVIDIA driver")

# PyTorch + Blackwell
try:
    import torch
    cuda_ver = torch.version.cuda or "none"
    ok = torch.cuda.is_available()
    arch = torch.cuda.get_arch_list() if ok else []
    blackwell = any("120" in a for a in arch)
    add("PASS" if ok else "FAIL", "PyTorch CUDA", f"torch {torch.__version__}, CUDA {cuda_ver}, "
        f"gpu={'yes: ' + torch.cuda.get_device_name(0) if ok else 'NO (install the cu128 build)'}")
    if ok:
        add("PASS" if blackwell else "FAIL", "PyTorch supports RTX 50 (sm_120)", ", ".join(arch))
        try:
            x = torch.randn(256, 256, device="cuda"); (x @ x).sum().item()
            add("PASS", "GPU math test", "matrix multiply ran on the GPU")
        except Exception as e:
            add("FAIL", "GPU math test", str(e)[:150])
except ImportError:
    add("FAIL", "PyTorch", "not installed: pip install torch --index-url https://download.pytorch.org/whl/cu128")

# CTranslate2 / faster-whisper
try:
    import ctranslate2
    n = ctranslate2.get_cuda_device_count()
    add("PASS" if n else "FAIL", "CTranslate2 (faster-whisper engine)", f"{ctranslate2.__version__}, cuda devices={n}, "
        f"types={sorted(ctranslate2.get_supported_compute_types('cuda')) if n else 'n/a'}")
    try:
        ver = tuple(int(p) for p in ctranslate2.__version__.split(".")[:2])
        if ver < (4, 5):
            add("WARN", "CTranslate2 version", "older than 4.5; run: pip install -U ctranslate2")
    except Exception:
        pass
except ImportError:
    add("FAIL", "CTranslate2", "pip install faster-whisper")
try:
    import faster_whisper; add("PASS", "faster-whisper", getattr(faster_whisper, "__version__", "installed"))
except ImportError:
    add("FAIL", "faster-whisper", "pip install faster-whisper")

# Other python packages
for mod, pipname in [("wordfreq", "wordfreq"), ("requests", "requests"), ("pytest", "pytest")]:
    try:
        __import__(mod); add("PASS", pipname)
    except ImportError:
        add("FAIL", pipname, f"pip install {pipname}")

# Ollama + Gemma
try:
    ver = json.load(urllib.request.urlopen("http://localhost:11434/api/version", timeout=5))["version"]
    add("PASS", "Ollama running", f"version {ver} (Gemma 4 needs 0.20.0 or newer)")
    tags = json.load(urllib.request.urlopen("http://localhost:11434/api/tags", timeout=5))
    names = [m["name"] for m in tags.get("models", [])]
    for need in ("gemma4:e4b", "gemma4:e2b"):
        add("PASS" if need in names else "FAIL", f"model {need}", "installed" if need in names else f"run: ollama pull {need}")
except Exception:
    add("FAIL", "Ollama", "not reachable at localhost:11434; install from ollama.com and start it")

# Tools + disk + where things are stored
add("PASS" if shutil.which("git") else "FAIL", "Git", shutil.which("git") or "install Git for Windows")
here = os.path.dirname(os.path.abspath(__file__))
free = shutil.disk_usage(here).free / 1e9
add("PASS" if free > 35 else "WARN", f"Free disk on project drive ({here[:2]})", f"{free:.0f} GB (need about 35 GB)")
def where(label, path):
    path = path or "(default, on C:)"
    on_c = os.name == "nt" and (path.upper().startswith("C:") or path.startswith("(default"))
    add("WARN" if on_c else "PASS", f"{label} stored at", path)
where("Project folder", here)
where("Whisper models (HF_HOME)", os.environ.get("HF_HOME"))
where("Gemma models (OLLAMA_MODELS)", os.environ.get("OLLAMA_MODELS"))

fails = [r for r in rows if r[0] == "FAIL"]
print(f"\n{len(rows) - len(fails)} OK or warning, {len(fails)} to fix." + ("" if fails else "  Setup complete."))
