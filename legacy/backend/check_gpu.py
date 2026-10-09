import sys

def check_gpu():
    print("=" * 50)
    print("      VERIFICACIÓN DE HARDWARE Y GPU (CUDA)      ")
    print("=" * 50)

    try:
        import torch
        print(f"[*] PyTorch Version : {torch.__version__}")
        
        cuda_available = torch.cuda.is_available()
        print(f"[*] CUDA Disponible : {'SÍ (GPU ACTIVA)' if cuda_available else 'NO (MODO CPU)'}")

        if cuda_available:
            device_count = torch.cuda.device_count()
            current_device = torch.cuda.current_device()
            device_name = torch.cuda.get_device_name(current_device)
            cuda_version = torch.version.cuda
            
            # Memoria en GB
            total_memory = torch.cuda.get_device_properties(current_device).total_memory / (1024 ** 3)
            allocated_memory = torch.cuda.memory_allocated(current_device) / (1024 ** 3)
            reserved_memory = torch.cuda.memory_reserved(current_device) / (1024 ** 3)

            print(f"[*] Dispositivos CUDA: {device_count}")
            print(f"[*] GPU Seleccionada: {device_name} (ID: {current_device})")
            print(f"[*] Versión CUDA    : {cuda_version}")
            print(f"[*] Memoria Total   : {total_memory:.2f} GB")
            print(f"[*] Memoria en Uso  : {allocated_memory:.2f} GB")
            print(f"[*] Memoria Reserva : {reserved_memory:.2f} GB")
            print("=" * 50)
            print(">> GPU NVIDIA detectada correctamente y lista para acelerar HOMR.")
            print("=" * 50)
            return True
        else:
            print("=" * 50)
            print(">> AVISO: PyTorch no detectó CUDA. Se ejecutará en modo CPU.")
            print(">> Si tienes una GPU NVIDIA, asegúrate de instalar PyTorch con soporte CUDA 12.1:")
            print(">> pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121")
            print("=" * 50)
            return False

    except ImportError:
        print("[!] ERROR: PyTorch no está instalado en el entorno actual.")
        print("    Ejecuta: pip install torch torchvision torchaudio")
        print("=" * 50)
        return False

if __name__ == "__main__":
    has_gpu = check_gpu()
    # Retorna 0 para no romper scripts de inicialización
    sys.exit(0)
