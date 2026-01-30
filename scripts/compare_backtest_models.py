"""
Multi-Model Backtesting Comparison Script

Trains multiple ML models and runs backtesting with each to compare results.
"""

import os
import sys
import json
import subprocess
import pandas as pd
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

def train_models_for_symbols(symbols, model_types):
    """Train multiple model types for specified symbols."""
    print("="*80)
    print("TRAINING MODELS")
    print("="*80)
    
    for model_type in model_types:
        print(f"\n🔧 Training {model_type} for {len(symbols)} symbols...")
        
        cmd = [
            "python", "scripts/train_ml_model.py",
            "--model_type", model_type,
            "--per-symbol"
        ]
        
        # Add symbols if specified
        if symbols:
            cmd.extend(["--symbols"] + symbols)
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            print(f"✅ {model_type} training completed")
        else:
            print(f"❌ {model_type} training failed:")
            print(result.stderr)


def run_backtest_with_model(model_type, config_path="backtesting/config.json"):
    """Run backtest with specified model type."""
    print(f"\n{'='*80}")
    print(f"🚀 Running backtest with {model_type}...")
    print(f"{'='*80}")
    sys.stdout.flush()
    
    # Update config to use this model type
    with open(config_path, 'r') as f:
        config = json.load(f)
    
    config['ml_filter']['model_type'] = model_type
    config['ml_filter']['enabled'] = True
    
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    
    # Use virtual environment Python if available
    venv_python = Path("trading_env/Scripts/python.exe")
    if venv_python.exists():
        python_cmd = str(venv_python)
    else:
        python_cmd = "python"
    
    # Run backtest with proper environment and show output in real-time
    env = os.environ.copy()
    env['PYTHONPATH'] = '.'
    env['PYTHONUNBUFFERED'] = '1'  # Force unbuffered output
    
    cmd = [python_cmd, "-u", "backtesting/main.py"]  # -u flag for unbuffered
    
    # Use Popen to stream output in real-time
    process = subprocess.Popen(
        cmd, 
        stdout=subprocess.PIPE, 
        stderr=subprocess.STDOUT,  # Merge stderr into stdout
        text=True,
        env=env,
        cwd=os.getcwd(),
        bufsize=0  # Unbuffered
    )
    
    # Collect output while showing it
    output_lines = []
    
    # Read stdout in real-time
    try:
        for line in iter(process.stdout.readline, ''):
            if line:
                print(line, end='', flush=True)  # Show progress immediately
                output_lines.append(line)
    except KeyboardInterrupt:
        process.kill()
        print("\n⚠️ Backtest interrupted by user")
        return None
    
    # Wait for process to complete
    process.wait()
    
    if process.returncode == 0:
        print(f"\n✅ Backtest with {model_type} completed successfully!")
        
        # Find the comparison table
        for i, line in enumerate(output_lines):
            if 'ML FILTER COMPARISON SUMMARY' in line:
                # Extract table lines
                table_start = i + 3  # Skip header lines
                table_lines = []
                for j in range(table_start, len(output_lines)):
                    if '===' in output_lines[j]:
                        break
                    if output_lines[j].strip() and not output_lines[j].startswith('['):
                        table_lines.append(output_lines[j])
                
                return parse_backtest_results(table_lines, model_type)
    else:
        print(f"\n❌ Backtest with {model_type} failed with code {process.returncode}!")
    
    return None


def parse_backtest_results(table_lines, model_type):
    """Parse backtest results from table lines."""
    results = {}
    
    for line in table_lines:
        parts = line.split()
        if len(parts) >= 10:
            symbol = parts[0]
            
            # Skip header lines (Symbol, Trades(B), etc.)
            if symbol in ['Symbol', 'Trades(B)', 'Elapsed', 'Time:']:
                continue
            
            # Try to parse, skip if fails
            try:
                results[symbol] = {
                    'model': model_type,
                    'trades_baseline': int(parts[1]),
                    'trades_ml': int(parts[2]),
                    'reduction_pct': float(parts[3].rstrip('%')),
                    'wr_baseline': float(parts[4].rstrip('%')),
                    'wr_ml': float(parts[5].rstrip('%')),
                    'wr_diff': float(parts[6].rstrip('%').lstrip('+')),
                    'pnl_baseline': float(parts[7].rstrip('%').lstrip('+')),
                    'pnl_ml': float(parts[8].rstrip('%').lstrip('+')),
                    'pnl_diff': float(parts[9].rstrip('%').lstrip('+'))
                }
            except (ValueError, IndexError):
                # Skip lines that can't be parsed
                continue
    
    return results


def create_comparison_table(all_results):
    """Create comprehensive comparison table across all models."""
    
    # Get all symbols
    symbols = set()
    for model_results in all_results.values():
        symbols.update(model_results.keys())
    
    symbols = sorted(symbols)
    
    print("\n" + "="*150)
    print("MULTI-MODEL BACKTESTING COMPARISON")
    print("="*150)
    
    # Header
    header = f"{'Symbol':<8} {'Baseline':<12}"
    for model in all_results.keys():
        header += f" {model:<35}"
    print(header)
    print("-" * 150)
    
    # Subheader
    subheader = f"{'':8} {'Trades  WR%':<12}"
    for _ in all_results.keys():
        subheader += f" {'Trades  WR%   PnL%   Reduc%':<35}"
    print(subheader)
    print("=" * 150)
    
    # Data rows
    for symbol in symbols:
        # Get baseline (should be same across all models)
        baseline_trades = None
        baseline_wr = None
        
        for model_results in all_results.values():
            if symbol in model_results:
                baseline_trades = model_results[symbol]['trades_baseline']
                baseline_wr = model_results[symbol]['wr_baseline']
                break
        
        if baseline_trades is None:
            continue
        
        row = f"{symbol:<8} {baseline_trades:>5}  {baseline_wr:>5.1f}%"
        
        for model, model_results in all_results.items():
            if symbol in model_results:
                r = model_results[symbol]
                row += f"  {r['trades_ml']:>5}  {r['wr_ml']:>5.1f}%  {r['pnl_diff']:>+6.1f}%  {r['reduction_pct']:>5.1f}%"
            else:
                row += f"  {'N/A':<35}"
        
        print(row)
    
    print("=" * 150)
    
    # Summary statistics
    print("\nSUMMARY STATISTICS:")
    print("-" * 150)
    
    for model, model_results in all_results.items():
        avg_wr_improvement = sum(r['wr_diff'] for r in model_results.values()) / len(model_results)
        avg_pnl_improvement = sum(r['pnl_diff'] for r in model_results.values()) / len(model_results)
        avg_reduction = sum(r['reduction_pct'] for r in model_results.values()) / len(model_results)
        
        print(f"{model:<15} Avg WR Δ: {avg_wr_improvement:>+6.2f}%  |  Avg PnL Δ: {avg_pnl_improvement:>+7.2f}%  |  Avg Reduction: {avg_reduction:>5.1f}%")
    
    print("=" * 150)
    
    # Save to file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = f"results/multi_model_comparison_{timestamp}.txt"
    
    os.makedirs("results", exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("="*150 + "\n")
        f.write("MULTI-MODEL BACKTESTING COMPARISON\n")
        f.write("="*150 + "\n\n")
        
        # Write table
        f.write(header + "\n")
        f.write("-" * 150 + "\n")
        f.write(subheader + "\n")
        f.write("=" * 150 + "\n")
        
        for symbol in symbols:
            baseline_trades = None
            baseline_wr = None
            
            for model_results in all_results.values():
                if symbol in model_results:
                    baseline_trades = model_results[symbol]['trades_baseline']
                    baseline_wr = model_results[symbol]['wr_baseline']
                    break
            
            if baseline_trades is None:
                continue
            
            row = f"{symbol:<8} {baseline_trades:>5}  {baseline_wr:>5.1f}%"
            
            for model, model_results in all_results.items():
                if symbol in model_results:
                    r = model_results[symbol]
                    row += f"  {r['trades_ml']:>5}  {r['wr_ml']:>5.1f}%  {r['pnl_diff']:>+6.1f}%  {r['reduction_pct']:>5.1f}%"
                else:
                    row += f"  {'N/A':<35}"
            
            f.write(row + "\n")
        
        f.write("=" * 150 + "\n\n")
        
        # Write summary
        f.write("SUMMARY STATISTICS:\n")
        f.write("-" * 150 + "\n")
        
        for model, model_results in all_results.items():
            avg_wr_improvement = sum(r['wr_diff'] for r in model_results.values()) / len(model_results)
            avg_pnl_improvement = sum(r['pnl_diff'] for r in model_results.values()) / len(model_results)
            avg_reduction = sum(r['reduction_pct'] for r in model_results.values()) / len(model_results)
            
            f.write(f"{model:<15} Avg WR Δ: {avg_wr_improvement:>+6.2f}%  |  Avg PnL Δ: {avg_pnl_improvement:>+7.2f}%  |  Avg Reduction: {avg_reduction:>5.1f}%\n")
        
        f.write("=" * 150 + "\n")
    
    print(f"\n📄 Results saved to: {output_file}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Compare multiple ML models via backtesting")
    parser.add_argument("--models", nargs="+", default=["RandomForest", "XGBoost", "LightGBM"],
                        help="Models to compare")
    parser.add_argument("--symbols", nargs="+", default=None,
                        help="Specific symbols to test (default: all)")
    parser.add_argument("--skip-training", action="store_true",
                        help="Skip training, use existing models")
    
    args = parser.parse_args()
    
    print("="*80)
    print("MULTI-MODEL BACKTESTING COMPARISON")
    print("="*80)
    print(f"Models: {', '.join(args.models)}")
    print(f"Symbols: {', '.join(args.symbols) if args.symbols else 'All'}")
    print("="*80)
    
    # Step 1: Train models (unless skipped)
    if not args.skip_training:
        train_models_for_symbols(args.symbols, args.models)
    else:
        print("\n⏭️  Skipping training, using existing models")
    
    # Step 2: Run backtests with each model
    all_results = {}
    
    for model_type in args.models:
        results = run_backtest_with_model(model_type)
        if results:
            all_results[model_type] = results
    
    # Step 3: Create comparison table
    if all_results:
        create_comparison_table(all_results)
    else:
        print("\n❌ No results to compare!")


if __name__ == "__main__":
    main()
