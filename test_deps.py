def test_dependencies():
    print("📦 Probando dependencias...")
    
    dependencies = [
        ('pandas', 'pandas'),
        ('numpy', 'numpy'),
        ('yfinance', 'yfinance'),
        ('schedule', 'schedule'),
        ('telegram', 'telegram'),
        ('dotenv', 'dotenv'),
    ]
    
    failed = []
    
    for dep_name, import_name in dependencies:
        try:
            __import__(import_name)
            print(f"✅ {dep_name}")
        except ImportError as e:
            print(f"❌ {dep_name}: {e}")
            failed.append(dep_name)
    
    try:
        import talib
        print("✅ TA-Lib")
    except ImportError as e:
        print(f"❌ TA-Lib: {e}")
        failed.append('TA-Lib')
    
    return len(failed) == 0

if __name__ == "__main__":
    success = test_dependencies()
    print(f"📊 Resultado: {'5/5 PERFECT' if success else 'FAILED'}")
