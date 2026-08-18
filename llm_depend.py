import subprocess
import platform
import time
import sys

def ollama_install():
    """
    Installs Ollama and required models based on user's OS.
    """
    os_check = platform.system()
    
    print(f"\n[{os_check} detected]")
    print("1. Windows")
    print("2. Linux / Mac")
    print("3. Exit")
    
    try:
        os_choice_ = int(input("Confirm your operating system (1-3): "))
    except ValueError:
        print("Invalid input. Please enter a number.")
        return

    if os_choice_ == 1 and os_check == "Windows":
        print("Installing Ollama for Windows, please wait...")
        subprocess.Popen("powershell -Command \"irm https://ollama.com/install.ps1 | iex\"", shell=True).wait()
        print('Install complete. If errors occur later, please restart your system/terminal.')
        
    elif os_choice_ == 2 and os_check in ["Linux", "Darwin"]:
        print("Installing Ollama for Linux/Mac, please wait...")
        subprocess.Popen("curl -fsSL https://ollama.com/install.sh | sh", shell=True).wait()
        print('Install complete. If errors occur later, please restart your system/terminal.')
        
    elif os_choice_ == 3:
        print("Exiting...")
        sys.exit()
    else:
        print("OS mismatch or invalid option. Please opt for manual installation: https://ollama.com")
        sys.exit()

    print('\nAttempting to start Ollama server...')
    try:
        subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(3)
    except Exception as e:
        print(f"Error starting Ollama server: {e}. A manual restart may be required.")
        sys.exit()

    try:
        ram_amt = int(input("\nEnter your RAM in GB or enter 9 or more if you have a 4GB+ dedicated GPU: "))
    except ValueError:
        ram_amt = 8

    # Select model size based on RAM
    if ram_amt <= 4:
        model = "qwen2.5:0.5b"
    elif ram_amt <= 8:
        model = "qwen2.5:1.5b"
    else:
        model = "qwen2.5:3b"

    print(f"Installing required model ({model}), please wait...")
    
    process = subprocess.Popen(["ollama", "pull", model])
    process.wait() 
    
    print('\nSetup finished successfully!')

if __name__ == "__main__":
    ollama_install()
