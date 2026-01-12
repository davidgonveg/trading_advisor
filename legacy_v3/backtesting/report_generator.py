#!/usr/bin/env python3
"""
📝 REPORT GENERATOR - Generación de Reportes
==========================================

Genera reportes completos del backtesting en múltiples formatos.
"""

import logging
import json
from datetime import datetime
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Generador de reportes de backtesting"""

    def __init__(self, output_dir: str = "backtesting/results"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"📝 ReportGenerator inicializado (output: {output_dir})")

    def generate_json_report(self, results: Dict, filename: str = None) -> str:
        """Generar reporte en JSON"""
        try:
            if not filename:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"backtest_results_{timestamp}.json"

            filepath = self.output_dir / filename

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, default=str)

            logger.info(f"✅ Reporte JSON generado: {filepath}")
            return str(filepath)

        except Exception as e:
            logger.error(f"❌ Error generando JSON: {e}")
            return ""

    def generate_summary_report(self, results: Dict, filename: str = None) -> str:
        """Generar reporte de resumen en texto"""
        try:
            if not filename:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"backtest_summary_{timestamp}.txt"

            filepath = self.output_dir / filename

            metrics = results.get('metrics', {})

            summary = f"""
╔═══════════════════════════════════════════════════════════════╗
║            REPORTE DE BACKTESTING - RESUMEN
╠═══════════════════════════════════════════════════════════════╣
║  Generado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
╠═══════════════════════════════════════════════════════════════╣
║
║  💰 RENDIMIENTO
║  ─────────────────────────────────────────────────────────────
║  Capital Inicial:        ${metrics.get('initial_capital', 0):,.2f}
║  Capital Final:          ${metrics.get('final_capital', 0):,.2f}
║  P&L Neto:               ${metrics.get('net_pnl', 0):,.2f}
║  Retorno:                {metrics.get('return_pct', 0):.2f}%
║
║  📊 TRADES
║  ─────────────────────────────────────────────────────────────
║  Total Trades:           {metrics.get('total_trades', 0)}
║  Ganadores:              {metrics.get('winning_trades', 0)} ({metrics.get('win_rate', 0):.1f}%)
║  Perdedores:             {metrics.get('losing_trades', 0)}
║
║  💹 MÉTRICAS
║  ─────────────────────────────────────────────────────────────
║  Profit Factor:          {metrics.get('profit_factor', 0):.2f}
║  Ganancia Promedio:      ${metrics.get('avg_win', 0):,.2f}
║  Pérdida Promedio:       ${metrics.get('avg_loss', 0):,.2f}
║  Mayor Ganancia:         ${metrics.get('largest_win', 0):,.2f}
║  Mayor Pérdida:          ${metrics.get('largest_loss', 0):,.2f}
║
║  📉 RIESGO
║  ─────────────────────────────────────────────────────────────
║  Max Drawdown:           {metrics.get('max_drawdown_pct', 0):.2f}%
║  Sharpe Ratio:           {metrics.get('sharpe_ratio', 0):.2f}
║  Comisiones Totales:     ${metrics.get('total_commissions', 0):,.2f}
║  Barras Promedio:        {metrics.get('avg_bars_held', 0):.0f}
║
╚═══════════════════════════════════════════════════════════════╝
"""

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(summary)

            logger.info(f"✅ Reporte de resumen generado: {filepath}")
            return str(filepath)

        except Exception as e:
            logger.error(f"❌ Error generando resumen: {e}")
            return ""

    def generate_trades_csv(self, results: Dict, filename: str = None) -> str:
        """Generar CSV con todos los trades"""
        try:
            if not filename:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                filename = f"backtest_trades_{timestamp}.csv"

            filepath = self.output_dir / filename

            trades = results.get('trades', [])

            if not trades:
                logger.warning("⚠️  No hay trades para exportar")
                return ""

            # Crear CSV simple
            import csv

            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=trades[0].keys())
                writer.writeheader()
                writer.writerows(trades)

            logger.info(f"✅ CSV de trades generado: {filepath} ({len(trades)} trades)")
            return str(filepath)

        except Exception as e:
            logger.error(f"❌ Error generando CSV: {e}")
            return ""

    def generate_all_reports(self, results: Dict) -> Dict[str, str]:
        """Generar todos los reportes"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        report_files = {
            'json': self.generate_json_report(results, f"results_{timestamp}.json"),
            'summary': self.generate_summary_report(results, f"summary_{timestamp}.txt"),
            'trades_csv': self.generate_trades_csv(results, f"trades_{timestamp}.csv"),
        }

        logger.info(f"✅ Todos los reportes generados en: {self.output_dir}")
        return report_files
