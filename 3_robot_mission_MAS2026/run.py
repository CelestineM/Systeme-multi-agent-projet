# ============================================================
# Group Number  : 3
# Date          : 13/03/2026
# Members       : Malo Chauvel, Constance Piquet, Célestine Martin
# ============================================================

import subprocess
import sys

if __name__ == "__main__":
    print("Démarrage du serveur Solara...")
    try:
        subprocess.run([sys.executable, "-m", "solara", "run", "server.py"])
    except KeyboardInterrupt:
        print("\nArrêt du serveur.")