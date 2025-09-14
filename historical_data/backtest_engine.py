def _validate_date_data(self, symbol: str, date: datetime) -> bool:
        """Validar que los datos para una fecha específica sean confiables"""
        if symbol not in self.validation_reports:
            return False
        
        report = self.validation_reports[symbol]
        
        # No tradear si la calidad general es muy baja
        if report.overall_quality == DataQuality.UNUSABLE:
            return False
        
        # No tradear en fechas cercanas a gaps grandes
        for gap in getattr(report, 'temporal_gaps', []):
            gap_start = gap.get('start')
            gap_end = gap.get('end')
            if gap_start and gap_end:
                # Evitar 2 días antes y después de gaps grandes
                if gap.get('days', 0) > 3:
                    if abs((date - gap_start).days) <= 2 or abs((date - gap_end).days) <= 2:
                        return False
        
        return True
    
    def _simulate_validated_signal(self, symbol: str, data: pd.DataFrame, 
                                  current_date: datetime) -> Optional[TradingSignal]:
        """Simular señal con validación de datos en tiempo real"""
        try:
            if current_date not in data.index:
                return None
            
            row = data.loc[current_date]
            
            # Validar que los indicadores para esta fecha sean válidos
            required_indicators = ['rsi_value', 'macd_histogram', 'vwap_value', 'close_price']
            for indicator in required_indicators:
                if indicator not in row or pd.isna(row[indicator]) or np.isinf(row[indicator]):
                    logger.debug(f"⚠️ {symbol} @ {current_date}: Invalid {indicator}")
                    return None
            
            # Validar rangos de indicadores
            if not (0 <= row.get('rsi_value', 50) <= 100):
                return None
            
            if row.get('close_price', 0) <= 0:
                return None
            
            # Reconstruir estructura de indicadores (código anterior...)
            indicators = {
                'symbol': symbol,
                'timestamp': current_date,
                'current_price': row['close_price'],
                'current_volume': row.get('volume', 0),
                
                'macd': {
                    'macd': row.get('macd_line', 0),
                    'signal': row.get('macd_signal', 0),
                    'histogram': row.get('macd_histogram', 0),
                    'bullish_cross': row.get('macd_histogram', 0) > 0,
                    'bearish_cross': row.get('macd_histogram', 0) < 0,
                    'signal_type': 'BULLISH' if row.get('macd_histogram', 0) > 0 else 'BEARISH',
                    'signal_strength': min(abs(row.get('macd_histogram', 0)) * 100, 20)
                },
                
                'rsi': {
                    'rsi': row.get('rsi_value', 50),
                    'oversold': row.get('rsi_value', 50) < 40,
                    'overbought': row.get('rsi_value', 50) > 60,
                    'signal_type': 'OVERSOLD' if row.get('rsi_value', 50) < 40 else 'OVERBOUGHT' if row.get('rsi_value', 50) > 60 else 'NEUTRAL',
                    'signal_strength': max(0, 20 - abs(row.get('rsi_value', 50) - 50)) if row.get('rsi_value', 50) < 40 or row.get('rsi_value', 50) > 60 else 0
                },
                
                'vwap': {
                    'vwap': row.get('vwap_value', row['close_price']),
                    'deviation_pct': row.get('vwap_deviation_pct', 0),
                    'signal_type': 'NEAR_VWAP' if abs(row.get('vwap_deviation_pct', 0)) <= 0.5 else 'ABOVE_VWAP' if row.get('vwap_deviation_pct', 0) > 0 else 'BELOW_VWAP',
                    'signal_strength': 15 if abs(row.get('vwap_deviation_pct', 0)) <= 0.5 else 10
                },
                
                'roc': {
                    'roc': row.get('roc_value', 0),
                    'bullish_momentum': row.get('roc_value', 0) > 1.5,
                    'bearish_momentum': row.get('roc_value', 0) < -1.5,
                    'signal_type': 'BULLISH' if row.get('roc_value', 0) > 1.5 else 'BEARISH' if row.get('roc_value', 0) < -1.5 else 'NEUTRAL',
                    'signal_strength': min(abs(row.get('roc_value', 0)) * 2, 15)
                },
                
                'bollinger': {
                    'upper_band': row.get('bb_upper', 0),
                    'middle_band': row.get('bb_middle', row['close_price']),
                    'lower_band': row.get('bb_lower', 0),
                    'bb_position': row.get('bb_position', 0.5),
                    'near_lower': row.get('bb_position', 0.5) < 0.2,
                    'near_upper': row.get('bb_position', 0.5) > 0.8,
                    'signal_type': 'LOWER_BAND' if row.get('bb_position', 0.5) < 0.2 else 'UPPER_BAND' if row.get('bb_position', 0.5) > 0.8 else 'NEUTRAL',
                    'signal_strength': 15 if row.get('bb_position', 0.5) < 0.2 or row.get('bb_position', 0.5) > 0.8 else 0
                },
                
                'volume_osc': {
                    'volume_oscillator': row.get('volume_oscillator', 0),
                    'high_volume': row.get('volume_oscillator', 0) > 50,
                    'signal_type': 'HIGH_VOLUME' if row.get('volume_oscillator', 0) > 50 else 'NORMAL',
                    'signal_strength': 10 if row.get('volume_oscillator', 0) > 50 else 0
                },
                
                'atr': {
                    'atr': row.get('atr_value', 0),
                    'atr_percentage': row.get('atr_percentage', 0),
                    'volatility_level': row.get('volatility_level', 'NORMAL')
                }
            }
            
            # Usar scanner para evaluar señal
            signal = self.scanner.evaluate_signal_from_indicators(indicators, current_date)
            
            if signal and signal.signal_strength >= config.SIGNAL_THRESHOLDS['NO_TRADE']:
                return signal
            
            return None
            
        except Exception as e:
            logger.debug(f"❌ Error simulating signal for {symbol} @ {current_date}: {e}")
            return None
    
    def _get_future_data(self, data: pd.DataFrame, current_date: datetime, periods: int) -> pd.DataFrame:
        """Obtener datos futuros validados"""
        try:
            current_idx = data.index.get_loc(current_date)
            end_idx = min(current_idx + periods, len(data))
            future_data = data.iloc[current_idx+1:end_idx]
            
            # Validar continuidad de datos futuros
            if len(future_data) < periods * 0.7:  # Mínimo 70% de datos esperados
                logger.debug(f"⚠️ Insufficient future data: {len(future_data)}/{periods}")
            
            return future_data
            
        except Exception as e:
            logger.debug(f"❌ Error getting future data: {e}")
            return pd.DataFrame()
    
    def _simulate_validated_trade(self, signal: TradingSignal, future_data: pd.DataFrame) -> Optional[BacktestTrade]:
        """Simular trade con validación y slippage realista"""
        try:
            # Calcular tamaño de posición
            position_size = self._calculate_position_size(signal)
            if position_size <= 0:
                return None
            
            # Aplicar slippage realista en entrada
            entry_slippage = self._calculate_slippage(signal.current_price, signal.current_volume)
            entry_price = signal.current_price * (1 + entry_slippage if signal.signal_type == "LONG" else 1 - entry_slippage)
            
            # Definir niveles de salida
            stop_loss_pct = 0.02
            take_profit_pct = 0.04
            max_hold_periods = 5
            
            if signal.signal_type == "LONG":
                stop_loss = entry_price * (1 - stop_loss_pct)
                take_profit = entry_price * (1 + take_profit_pct)
            else:  # SHORT
                stop_loss = entry_price * (1 + stop_loss_pct)
                take_profit = entry_price * (1 - take_profit_pct)
            
            # Simular evolución del trade con validación continua
            data_quality_score = self.validation_reports[signal.symbol].quality_score
            execution_issues = []
            
            max_favorable = 0.0
            max_adverse = 0.0
            
            for i, (idx, row) in enumerate(future_data.iterrows()):
                # Validar calidad de datos para este período
                if pd.isna(row['close_price']) or row['close_price'] <= 0:
                    execution_issues.append(f"Invalid price data @ {idx}")
                    continue
                
                # Detectar gaps de precio
                if i > 0:
                    prev_price = future_data.iloc[i-1]['close_price']
                    price_change = abs(row['close_price'] - prev_price) / prev_price
                    if price_change > 0.1:  # Gap >10%
                        execution_issues.append(f"Price gap {price_change:.1%} @ {idx}")
                
                current_price = row['close_price']
                
                # Calcular MFE y MAE
                if signal.signal_type == "LONG":
                    unrealized_pct = (current_price - entry_price) / entry_price
                    max_favorable = max(max_favorable, unrealized_pct)
                    max_adverse = min(max_adverse, unrealized_pct)
                    
                    # Check exit conditions con slippage
                    if current_price <= stop_loss:
                        exit_slippage = self._calculate_slippage(stop_loss, row.get('volume', 0))
                        exit_price = stop_loss * (1 - exit_slippage)  # Slippage negativo en stop loss
                        exit_reason = "STOP_LOSS"
                        exit_time = idx
                        break
                    elif current_price >= take_profit:
                        exit_slippage = self._calculate_slippage(take_profit, row.get('volume', 0))
                        exit_price = take_profit * (1 - exit_slippage)  # Slippage negativo en take profit
                        exit_reason = "TAKE_PROFIT"
                        exit_time = idx
                        break
                        
                else:  # SHORT
                    unrealized_pct = (entry_price - current_price) / entry_price
                    max_favorable = max(max_favorable, unrealized_pct)
                    max_adverse = min(max_adverse, unrealized_pct)
                    
                    if current_price >= stop_loss:
                        exit_slippage = self._calculate_slippage(stop_loss, row.get('volume', 0))
                        exit_price = stop_loss * (1 + exit_slippage)  # Slippage positivo en stop loss SHORT
                        exit_reason = "STOP_LOSS"
                        exit_time = idx
                        break
                    elif current_price <= take_profit:
                        exit_slippage = self._calculate_slippage(take_profit, row.get('volume', 0))
                        exit_price = take_profit * (1 + exit_slippage)  # Slippage positivo en take profit SHORT
                        exit_reason = "TAKE_PROFIT"
                        exit_time = idx
                        break
                
                # Límite de tiempo
                if i >= max_hold_periods:
                    exit_slippage = self._calculate_slippage(current_price, row.get('volume', 0))
                    exit_price = current_price * (1 - exit_slippage if signal.signal_type == "LONG" else 1 + exit_slippage)
                    exit_reason = "TIME_LIMIT"
                    exit_time = idx
                    break
            else:
                # Salir al final de los datos
                final_row = future_data.iloc[-1]
                exit_slippage = self._calculate_slippage(final_row['close_price'], final_row.get('volume', 0))
                exit_price = final_row['close_price'] * (1 - exit_slippage if signal.signal_type == "LONG" else 1 + exit_slippage)
                exit_reason = "END_OF_DATA"
                exit_time = future_data.index[-1]
            
            # Calcular resultados con comisiones
            if signal.signal_type == "LONG":
                pnl_pct = (exit_price - entry_price) / entry_price
                pnl_dollars = position_size * (exit_price - entry_price)
            else:  # SHORT
                pnl_pct = (entry_price - exit_price) / entry_price
                pnl_dollars = position_size * (entry_price - exit_price)
            
            # Aplicar comisiones
            position_value = position_size * entry_price
            commission_cost = position_value * self.commission * 2  # Entry + exit
            pnl_dollars -= commission_cost
            
            # Tiempo de retención
            hold_time_hours = (exit_time - signal.timestamp).total_seconds() / 3600
            
            # Calcular slippage total
            total_slippage = entry_slippage + exit_slippage
            
            trade = BacktestTrade(
                symbol=signal.symbol,
                direction=signal.signal_type,
                entry_signal=signal,
                entry_time=signal.timestamp,
                entry_price=entry_price,
                position_size=position_size,
                exit_time=exit_time,
                exit_price=exit_price,
                exit_reason=exit_reason,
                pnl_dollars=pnl_dollars,
                pnl_percent=pnl_pct,
                hold_time_hours=hold_time_hours,
                max_favorable_excursion=max_favorable,
                max_adverse_excursion=max_adverse,
                data_quality_score=data_quality_score,
                price_slippage=total_slippage,
                execution_issues=execution_issues
            )
            
            # Actualizar balance
            self.account_balance += pnl_dollars
            
            logger.debug(f"✅ Validated trade: {signal.symbol} {signal.signal_type} "
                        f"PnL: ${pnl_dollars:.2f} Quality: {data_quality_score:.1f}")
            
            return trade
            
        except Exception as e:
            logger.error(f"❌ Error in validated trade simulation: {e}")
            return None
    
    def _calculate_position_size(self, signal: TradingSignal) -> float:
        """Calcular tamaño de posición (igual que antes)"""
        try:
            if signal.position_plan:
                risk_amount = self.account_balance * signal.position_plan.total_risk_percent / 100
            else:
                risk_amount = self.account_balance * self.position_size_pct
            
            shares = risk_amount / signal.current_price
            max_position_value = self.account_balance * 0.1
            max_shares = max_position_value / signal.current_price
            
            return min(shares, max_shares)
            
        except Exception:
            return 0
    
    def _calculate_slippage(self, price: float, volume: float) -> float:
        """Calcular slippage realista basado en volumen"""
        try:
            base_slippage = self.slippage_bps / 10000  # Convertir basis points a decimal
            
            # Penalizar volumen bajo
            if volume < 100000:  # Volumen muy bajo
                slippage_multiplier = 2.0
            elif volume < 500000:  # Volumen bajo
                slippage_multiplier = 1.5
            else:  # Volumen normal/alto
                slippage_multiplier = 1.0
            
            return base_slippage * slippage_multiplier
            
        except Exception:
            return self.slippage_bps / 10000
    
    def _calculate_validated_metrics(self, start_date: datetime, end_date: datetime, 
                                   symbols: List[str]) -> BacktestMetrics:
        """Calcular métricas incluyendo información de validación"""
        
        # Métricas básicas (reutilizar código anterior)
        if not self.trades:
            return self._create_empty_metrics(start_date, end_date)
        
        # Calcular métricas estándar
        total_trades = len(self.trades)
        winning_trades = len([t for t in self.trades if t.pnl_dollars > 0])
        losing_trades = total_trades - winning_trades
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        total_pnl = sum(t.pnl_dollars for t in self.trades)
        wins = [t.pnl_dollars for t in self.trades if t.pnl_dollars > 0]
        losses = [t.pnl_dollars for t in self.trades if t.pnl_dollars < 0]
        
        average_win = np.mean(wins) if wins else 0
        average_loss = np.mean(losses) if losses else 0
        
        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        # Calcular métricas adicionales de validación
        avg_data_quality = np.mean([r.quality_score for r in self.validation_reports.values()])
        trades_on_poor_data = len([t for t in self.trades if t.data_quality_score < 60])
        
        # Score de confiabilidad del backtest
        quality_penalty = max(0, (75 - avg_data_quality) / 75)  # Penalizar si calidad < 75
        execution_penalty = trades_on_poor_data / total_trades if total_trades > 0 else 0
        reliability_score = (1 - quality_penalty - execution_penalty) * 100
        
        # Drawdown y Sharpe (simplificados)
        equity_values = [eq[1] for eq in self.equity_curve]
        if equity_values:
            running_max = np.maximum.accumulate(equity_values)
            drawdowns = (equity_values - running_max) / running_max
            max_drawdown = min(drawdowns) if len(drawdowns) > 0 else 0
        else:
            max_drawdown = 0
        
        # Sharpe ratio simplificado
        if len(self.equity_curve) > 1:
            returns = []
            for i in range(1, len(self.equity_curve)):
                prev_balance = self.equity_curve[i-1][1]
                curr_balance = self.equity_curve[i][1]
                ret = (curr_balance - prev_balance) / prev_balance if prev_balance > 0 else 0
                returns.append(ret)
            
            if returns:
                avg_return = np.mean(returns)
                return_std = np.std(returns)
                sharpe_ratio = (avg_return / return_std * np.sqrt(252)) if return_std > 0 else 0
            else:
                sharpe_ratio = 0
        else:
            sharpe_ratio = 0
        
        # Buy & hold
        buy_hold_return = self._calculate_buy_hold_return(symbols[0] if symbols else 'SPY', start_date, end_date)
        strategy_return = (self.account_balance - self.initial_balance) / self.initial_balance
        excess_return = strategy_return - buy_hold_return
        
        # Trade distribution
        trade_returns = [t.pnl_dollars for t in self.trades]
        best_trade = max(trade_returns) if trade_returns else 0
        worst_trade = min(trade_returns) if trade_returns else 0
        avg_hold_time = np.mean([t.hold_time_hours for t in self.trades]) if self.trades else 0
        
        return BacktestMetrics(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            total_pnl=total_pnl,
            average_win=average_win,
            average_loss=average_loss,
            profit_factor=profit_factor,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            max_drawdown_duration=0,  # Simplificado
            buy_hold_return=buy_hold_return,
            excess_return=excess_return,
            best_trade=best_trade,
            worst_trade=worst_trade,
            avg_hold_time=avg_hold_time,
            start_date=start_date,
            end_date=end_date,
            total_days=(end_date - start_date).days,
            
            # Métricas de validación
            data_quality_reports=self.validation_reports,
            avg_data_quality=avg_data_quality,
            trades_on_poor_data=trades_on_poor_data,
            reliability_score=reliability_score
        )
    
    def _calculate_buy_hold_return(self, symbol: str, start_date: datetime, end_date: datetime) -> float:
        """Calcular Buy & Hold return"""
        try:
            data = self.get_historical_data(symbol, start_date, end_date)
            if len(data) < 2:
                return 0.0
            
            start_price = data.iloc[0]['close_price']
            end_price = data.iloc[-1]['close_price']
            
            return (end_price - start_price) / start_price
            
        except Exception:
            return 0.0
    
    def _create_empty_metrics(self, start_date: datetime, end_date: datetime) -> BacktestMetrics:
        """Crear métricas vacías"""
        return BacktestMetrics(
            total_trades=0, winning_trades=0, losing_trades=0, win_rate=0.0,
            total_pnl=0.0, average_win=0.0, average_loss=0.0, profit_factor=0.0,
            sharpe_ratio=0.0, max_drawdown=0.0, max_drawdown_duration=0,
            buy_hold_return=0.0, excess_return=0.0, best_trade=0.0, worst_trade=0.0,
            avg_hold_time=0.0, start_date=start_date, end_date=end_date,
            total_days=(end_date - start_date).days,
            data_quality_reports=self.validation_reports,
            avg_data_quality=0.0, trades_on_poor_data=0, reliability_score=0.0
        )
    
    def print_validation_summary(self):
        """Imprimir resumen de validación de datos"""
        if not self.validation_reports:
            print("No validation data available")
            return
        
        print("=" * 60)
        print("🔍 DATA VALIDATION SUMMARY")
        print("=" * 60)
        
        quality_counts = {q: 0 for q in DataQuality}
        for report in self.validation_reports.values():
            quality_counts[report.overall_quality] += 1
        
        print(f"📊 Data Quality Distribution:")
        for quality, count in quality_counts.items():
            if count > 0:
                emoji = {"EXCELLENT": "🟢", "GOOD": "🔵", "FAIR": "🟡", "POOR": "🟠", "UNUSABLE": "🔴"}
                print(f"   {emoji.get(quality.value, '❓')} {quality.value}: {count} symbols")
        
        avg_quality = np.mean([r.quality_score for r in self.validation_reports.values()])
        print(f"\n📈 Average Data Quality: {avg_quality:.1f}/100")
        
        # Top issues
        all_warnings = []
        for report in self.validation_reports.values():
            all_warnings.extend(report.warnings)
        
        if all_warnings:
            from collections import Counter
            common_issues = Counter(all_warnings).most_common(5)
            print(f"\n⚠️ Most Common Issues:")
            for issue, count in common_issues:
                print(f"   • {issue} ({count} symbols)")
    
    def print_summary(self, metrics: BacktestMetrics):
        """Imprimir resumen completo incluyendo validación"""
        print("=" * 60)
        print("📊 VALIDATED BACKTEST SUMMARY")
        print("=" * 60)
        
        # Información de validación
        print(f"🔍 DATA QUALITY:")
        print(f"   Average Quality Score: {metrics.avg_data_quality:.1f}/100")
        print(f"   Reliability Score: {metrics.reliability_score:.1f}/100")
        print(f"   Trades on Poor Data: {metrics.trades_on_poor_data}/{metrics.total_trades}")
        print()
        
        # Métricas estándar
        print(f"📅 Period: {metrics.start_date.strftime('%Y-%m-%d')} to {metrics.end_date.strftime('%Y-%m-%d')} ({metrics.total_days} days)")
        print(f"💰 Initial Balance: ${self.initial_balance:,.2f}")
        print(f"💰 Final Balance: ${self.account_balance:,.2f}")
        
        total_return = (self.account_balance - self.initial_balance) / self.initial_balance
        print(f"📈 Total Return: {total_return:.2%}")
        print(f"📊 Buy & Hold: {metrics.buy_hold_return:.2%}")
        print(f"⚡ Excess Return: {metrics.excess_return:+.2%}")
        print()
        
        print("🎯 TRADE STATISTICS:")
        print(f"   Total Trades: {metrics.total_trades}")
        print(f"   Win Rate: {metrics.win_rate:.1%} ({metrics.winning_trades}W / {metrics.losing_trades}L)")
        print(f"   Profit Factor: {metrics.profit_factor:.2f}")
        print(f"   Average Win: ${metrics.average_win:,.2f}")
        print(f"   Average Loss: ${metrics.average_loss:,.2f}")
        print(f"   Best Trade: ${metrics.best_trade:,.2f}")
        print(f"   Worst Trade: ${metrics.worst_trade:,.2f}")
        print()
        
        print("📉 RISK METRICS:")
        print(f"   Sharpe Ratio: {metrics.sharpe_ratio:.2f}")
        print(f"   Max Drawdown: {metrics.max_drawdown:.2%}")
        print(f"   Avg Hold Time: {metrics.avg_hold_time:.1f} hours")
        print()
        
        # Interpretación con consideración de calidad de datos
        print("🎯 RELIABILITY ASSESSMENT:")
        
        if metrics.reliability_score >= 80:
            print("   ✅ High reliability - Results are trustworthy")
        elif metrics.reliability_score >= 60:
            print("   ⚡ Moderate reliability - Results should be interpreted with caution")
        else:
            print("   ❌ Low reliability - Results may not be representative")
        
        if metrics.avg_data_quality < 60:
            print("   ⚠️ Poor data quality detected - Consider getting better historical data")
        
        if metrics.trades_on_poor_data > metrics.total_trades * 0.2:
            print("   ⚠️ High percentage of trades executed on poor quality data")

def main():
    """Función principal CLI con validación"""
    parser = argparse.ArgumentParser(description='Validated Backtest Engine V5.0')
    parser.add_argument('--symbols', nargs='+', default=['AAPL', 'MSFT', 'GOOGL'], 
                       help='Símbolos a testear')
    parser.add_argument('--start-date', help='Fecha de inicio (YYYY-MM-DD)')
    parser.add_argument('--end-date', help='Fecha de fin (YYYY-MM-DD)')
    parser.add_argument('--balance', type=float, default=10000, 
                       help='Saldo inicial de la cuenta')
    parser.add_argument('--strict', action='store_true', 
                       help='Modo estricto: rechazar datos de baja calidad')
    parser.add_argument('--validation-only', action='store_true',
                       help='Solo validar datos, no ejecutar backtest')
    parser.add_argument('--quick', action='store_true', 
                       help='Test rápido con configuración limitada')
    
    args = parser.parse_args()
    
    # Configurar parámetros
    symbols = args.symbols
    balance = args.balance
    strict_mode = args.strict
    
    # Parse dates
    start_date = None
    end_date = None
    
    if args.start_date:
        start_date = datetime.strptime(args.start_date, '%Y-%m-%d')
    if args.end_date:
        end_date = datetime.strptime(args.end_date, '%Y-%m-%d')
    
    # Quick test configuration
    if args.quick:
        symbols = symbols[:1]
        if not start_date:
            start_date = datetime.now() - timedelta(days=30)
        if not end_date:
            end_date = datetime.now()
        print("⚡ QUICK TEST MODE: Limited symbols and time period")
    else:
        if not start_date:
            start_date = datetime.now() - timedelta(days=90)
        if not end_date:
            end_date = datetime.now()
    
    print(f"🚀 VALIDATED BACKTEST ENGINE V5.0")
    print("=" * 50)
    print(f"🔍 Data Validation: {'STRICT' if strict_mode else 'PERMISSIVE'} mode")
    
    # Crear engine
    engine = ValidatedBacktestEngine(account_balance=balance, strict_mode=strict_mode)
    
    try:
        if args.validation_only:
            # Solo validación de datos
            print(f"🔍 VALIDATION-ONLY MODE")
            validation_reports = engine.validate_all_data(symbols, start_date, end_date)
            engine.print_validation_summary()
            
            # Mostrar detalles por símbolo
            print(f"\n📋 DETAILED VALIDATION RESULTS:")
            print("-" * 60)
            
            for symbol, report in validation_reports.items():
                quality_emoji = {
                    DataQuality.EXCELLENT: "🟢",
                    DataQuality.GOOD: "🔵", 
                    DataQuality.FAIR: "🟡",
                    DataQuality.POOR: "🟠",
                    DataQuality.UNUSABLE: "🔴"
                }
                
                emoji = quality_emoji.get(report.overall_quality, "❓")
                print(f"{emoji} {symbol}:")
                print(f"   Quality: {report.overall_quality.value} ({report.quality_score:.1f}/100)")
                print(f"   Data Coverage: {report.actual_periods}/{report.total_expected_periods} periods ({100-report.gap_percentage:.1f}%)")
                print(f"   Largest Gap: {report.largest_gap_days} days")
                print(f"   Price Anomalies: {len(report.price_anomalies)}")
                print(f"   Usable for Backtest: {'✅ Yes' if report.usable_for_backtest else '❌ No'}")
                
                if report.warnings:
                    print(f"   ⚠️ Warnings: {len(report.warnings)}")
                    for warning in report.warnings[:3]:  # Show first 3 warnings
                        print(f"      • {warning}")
                    if len(report.warnings) > 3:
                        print(f"      ... and {len(report.warnings) - 3} more")
                        
                if report.recommendations:
                    print(f"   💡 Recommendations:")
                    for rec in report.recommendations[:2]:  # Show first 2 recommendations
                        print(f"      • {rec}")
                print()
            
        else:
            # Backtest completo con validación
            metrics = engine.run_backtest(
                symbols=symbols,
                start_date=start_date,
                end_date=end_date
            )
            
            # Mostrar validación primero
            engine.print_validation_summary()
            print()
            
            # Mostrar resultados del backtest
            engine.print_summary(metrics)
            
            # Recomendaciones finales
            print(f"\n💡 RECOMMENDATIONS:")
            
            if metrics.reliability_score < 60:
                print("   🔴 CRITICAL: Low reliability score - results may not be trustworthy")
                print("      → Download more complete historical data")
                print("      → Use --strict mode to exclude poor quality data")
                print("      → Consider shorter time period with better data coverage")
            
            elif metrics.reliability_score < 80:
                print("   🟡 CAUTION: Moderate reliability - interpret results carefully")
                print("      → Some data quality issues detected")
                print("      → Consider validating key trades manually")
            
            else:
                print("   ✅ HIGH RELIABILITY: Results are trustworthy")
                
            if metrics.total_trades == 0:
                print("   📊 No trades executed - possible causes:")
                print("      → Signal thresholds too strict")
                print("      → Insufficient historical data")
                print("      → All symbols excluded due to data quality")
                print("      → Run with --validation-only to check data availability")
                
            elif metrics.total_trades < 10:
                print("   📊 Limited trades - consider:")
                print("      → Longer time period")
                print("      → More symbols")
                print("      → Lower signal thresholds")
                
            else:
                print("   📊 Good trade sample size for statistical significance")
                
            # Data quality specific recommendations
            if metrics.avg_data_quality < 70:
                print("   📈 Data Quality Improvements:")
                print("      → Download more recent data with python downloader.py")
                print("      → Check for missing trading days or holidays")
                print("      → Verify indicator calculations are correct")
            
            print(f"\n🎉 Validated backtest completed!")
            
    except KeyboardInterrupt:
        print("\n🛑 Backtest interrupted by user")
    except Exception as e:
        logger.error(f"❌ Backtest failed: {e}")
        print(f"❌ Error: {e}")
        print("💡 Troubleshooting steps:")
        print("   1. Make sure historical data is available (run populate_db.py)")
        print("   2. Check database connection")
        print("   3. Verify symbols have sufficient data coverage")
        print("   4. Try --validation-only to check data quality first")

if __name__ == "__main__":
    main()
#!/usr/bin/env python3
"""
📊 BACKTEST ENGINE V5.0 - TRADING SYSTEM WITH DATA VALIDATION
============================================================

Motor de backtesting robusto con validación completa de datos históricos:

🔍 DATA VALIDATION LAYER:
- Detecta gaps temporales y datos faltantes
- Valida calidad de indicadores técnicos
- Identifica anomalías de precios/volumen
- Maneja weekends y holidays correctamente
- Verifica continuidad antes de simular trades

🚀 TRADING SIMULATION:
- Simulación realista con slippage y spread
- Validación de liquidez mínima
- Manejo de gaps de precio
- Exit conditions robustas

PHILOSOPHY: "Mejor no tradear que tradear con datos malos"
"""

import os
import sys
import pandas as pd
import numpy as np
import logging
import argparse
import json
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Union, Any, NamedTuple
from dataclasses import dataclass, asdict
import time
import warnings
from enum import Enum

# Paths para importar desde sistema principal
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
sys.path.insert(0, project_root)

# Imports del sistema principal
try:
    import config
    from database.connection import get_connection
    from scanner import SignalScanner, TradingSignal
    from indicators import TechnicalIndicators
    from position_calculator import PositionCalculator, PositionPlan
    print("✅ Todos los módulos del sistema importados correctamente")
except ImportError as e:
    print(f"❌ Error importing modules: {e}")
    print("💡 Asegúrate de estar en historical_data/ y que el sistema principal esté disponible")
    sys.exit(1)

# Configurar logging
logging.basicConfig(
    level=getattr(logging, getattr(config, 'LOG_LEVEL', 'INFO'), 'INFO'),
    format='%(levelname)s:%(name)s:%(message)s'
)
logger = logging.getLogger(__name__)
warnings.filterwarnings('ignore')

class DataQuality(Enum):
    """Niveles de calidad de datos"""
    EXCELLENT = "EXCELLENT"    # <1% gaps, todos los indicadores válidos
    GOOD = "GOOD"             # 1-5% gaps, indicadores mayormente válidos  
    FAIR = "FAIR"             # 5-15% gaps, algunos problemas de indicadores
    POOR = "POOR"             # >15% gaps, muchos indicadores inválidos
    UNUSABLE = "UNUSABLE"     # Datos insuficientes o muy corruptos

@dataclass
class DataValidationReport:
    """Reporte de validación de datos"""
    symbol: str
    start_date: datetime
    end_date: datetime
    
    # Métricas temporales
    total_expected_periods: int
    actual_periods: int
    missing_periods: int
    gap_percentage: float
    largest_gap_days: int
    
    # Métricas de indicadores
    indicators_with_nan: List[str]
    indicators_with_inf: List[str]
    indicators_outside_bounds: Dict[str, int]
    
    # Métricas de precios
    price_anomalies: List[Dict]  # Saltos >10% día a día
    volume_anomalies: List[Dict]  # Volumen 0 o >5x promedio
    
    # Calidad final
    overall_quality: DataQuality
    quality_score: float  # 0-100
    usable_for_backtest: bool
    warnings: List[str]
    recommendations: List[str]

class DataValidator:
    """Validador robusto de datos históricos"""
    
    def __init__(self):
        self.validation_thresholds = {
            'max_gap_percentage': 15.0,    # Máximo 15% de datos faltantes
            'max_single_gap_days': 7,      # Máximo gap de 7 días consecutivos
            'max_price_jump': 0.15,        # Máximo salto de precio 15%
            'min_volume_periods': 0.8,     # Mínimo 80% períodos con volumen
            'max_zero_volume_streak': 3,   # Máximo 3 días consecutivos sin volumen
            'indicator_nan_threshold': 0.1 # Máximo 10% indicadores con NaN
        }
    
    def validate_symbol_data(self, symbol: str, data: pd.DataFrame, 
                           start_date: datetime, end_date: datetime) -> DataValidationReport:
        """
        Validar datos históricos de un símbolo completo
        
        Args:
            symbol: Símbolo a validar
            data: DataFrame con datos históricos
            start_date: Fecha esperada de inicio
            end_date: Fecha esperada de fin
            
        Returns:
            DataValidationReport completo
        """
        logger.info(f"🔍 Validating data quality for {symbol}...")
        
        # Validaciones temporales
        temporal_metrics = self._validate_temporal_continuity(data, start_date, end_date)
        
        # Validaciones de indicadores
        indicator_metrics = self._validate_indicators_quality(data)
        
        # Validaciones de precios
        price_metrics = self._validate_price_quality(data)
        
        # Validaciones de volumen
        volume_metrics = self._validate_volume_quality(data)
        
        # Calcular calidad general
        quality_score = self._calculate_quality_score(
            temporal_metrics, indicator_metrics, price_metrics, volume_metrics
        )
        
        overall_quality = self._determine_quality_level(quality_score)
        usable = quality_score >= 60.0  # Mínimo 60% calidad para backtest
        
        # Generar warnings y recomendaciones
        warnings, recommendations = self._generate_warnings_and_recommendations(
            temporal_metrics, indicator_metrics, price_metrics, volume_metrics
        )
        
        report = DataValidationReport(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            total_expected_periods=temporal_metrics['expected_periods'],
            actual_periods=temporal_metrics['actual_periods'],
            missing_periods=temporal_metrics['missing_periods'],
            gap_percentage=temporal_metrics['gap_percentage'],
            largest_gap_days=temporal_metrics['largest_gap_days'],
            indicators_with_nan=indicator_metrics['nan_indicators'],
            indicators_with_inf=indicator_metrics['inf_indicators'],
            indicators_outside_bounds=indicator_metrics['outlier_indicators'],
            price_anomalies=price_metrics['anomalies'],
            volume_anomalies=volume_metrics['anomalies'],
            overall_quality=overall_quality,
            quality_score=quality_score,
            usable_for_backtest=usable,
            warnings=warnings,
            recommendations=recommendations
        )
        
        logger.info(f"✅ {symbol} validation complete: {overall_quality.value} ({quality_score:.1f}/100)")
        return report
    
    def _validate_temporal_continuity(self, data: pd.DataFrame, 
                                    start_date: datetime, end_date: datetime) -> Dict:
        """Validar continuidad temporal de los datos"""
        if data.empty:
            return {
                'expected_periods': 0,
                'actual_periods': 0,
                'missing_periods': 0,
                'gap_percentage': 100.0,
                'largest_gap_days': 0,
                'gaps': []
            }
        
        # Generar serie temporal esperada (solo días laborables)
        expected_dates = pd.bdate_range(start=start_date, end=end_date, freq='B')
        actual_dates = data.index
        
        # Calcular gaps
        missing_dates = expected_dates.difference(actual_dates)
        gap_percentage = len(missing_dates) / len(expected_dates) * 100
        
        # Encontrar gaps consecutivos
        gaps = []
        if len(missing_dates) > 0:
            missing_sorted = missing_dates.sort_values()
            gap_start = missing_sorted[0]
            gap_size = 1
            
            for i in range(1, len(missing_sorted)):
                if (missing_sorted[i] - missing_sorted[i-1]).days == 1:
                    gap_size += 1
                else:
                    gaps.append({
                        'start': gap_start,
                        'end': missing_sorted[i-1],
                        'days': gap_size
                    })
                    gap_start = missing_sorted[i]
                    gap_size = 1
            
            # Agregar último gap
            gaps.append({
                'start': gap_start,
                'end': missing_sorted[-1],
                'days': gap_size
            })
        
        largest_gap = max([g['days'] for g in gaps]) if gaps else 0
        
        return {
            'expected_periods': len(expected_dates),
            'actual_periods': len(actual_dates),
            'missing_periods': len(missing_dates),
            'gap_percentage': gap_percentage,
            'largest_gap_days': largest_gap,
            'gaps': gaps
        }
    
    def _validate_indicators_quality(self, data: pd.DataFrame) -> Dict:
        """Validar calidad de indicadores técnicos"""
        indicator_columns = [
            'rsi_value', 'macd_line', 'macd_signal', 'macd_histogram',
            'vwap_value', 'roc_value', 'bb_upper', 'bb_middle', 'bb_lower',
            'volume_oscillator', 'atr_value'
        ]
        
        nan_indicators = []
        inf_indicators = []
        outlier_indicators = {}
        
        # Definir rangos válidos para cada indicador
        valid_ranges = {
            'rsi_value': (0, 100),
            'macd_line': (-float('inf'), float('inf')),  # Sin límite específico
            'vwap_value': (0, float('inf')),  # Debe ser positivo
            'roc_value': (-100, 100),  # Cambio porcentual típico
            'volume_oscillator': (-100, 100),
            'atr_value': (0, float('inf'))  # Debe ser positivo
        }
        
        for col in indicator_columns:
            if col not in data.columns:
                continue
                
            values = data[col]
            
            # Check NaN
            nan_count = values.isna().sum()
            if nan_count > len(values) * 0.1:  # >10% NaN
                nan_indicators.append(col)
            
            # Check infinitos
            inf_count = np.isinf(values).sum()
            if inf_count > 0:
                inf_indicators.append(col)
            
            # Check outliers (valores fuera de rango esperado)
            if col in valid_ranges:
                min_val, max_val = valid_ranges[col]
                outliers = ((values < min_val) | (values > max_val)).sum()
                if outliers > 0:
                    outlier_indicators[col] = int(outliers)
        
        return {
            'nan_indicators': nan_indicators,
            'inf_indicators': inf_indicators,
            'outlier_indicators': outlier_indicators
        }
    
    def _validate_price_quality(self, data: pd.DataFrame) -> Dict:
        """Validar calidad de datos de precios"""
        anomalies = []
        
        if 'close_price' not in data.columns or len(data) < 2:
            return {'anomalies': anomalies}
        
        prices = data['close_price']
        
        # Calcular cambios día a día
        price_changes = prices.pct_change()
        
        # Detectar saltos anómalos (>15% en un día)
        large_moves = price_changes.abs() > self.validation_thresholds['max_price_jump']
        
        for idx in data.index[large_moves]:
            if pd.isna(price_changes.loc[idx]):
                continue
                
            anomalies.append({
                'date': idx,
                'type': 'price_jump',
                'value': price_changes.loc[idx],
                'price_before': prices.loc[prices.index[prices.index.get_loc(idx)-1]] if prices.index.get_loc(idx) > 0 else None,
                'price_after': prices.loc[idx]
            })
        
        return {'anomalies': anomalies}
    
    def _validate_volume_quality(self, data: pd.DataFrame) -> Dict:
        """Validar calidad de datos de volumen"""
        anomalies = []
        
        if 'volume' not in data.columns:
            return {'anomalies': anomalies}
        
        volume = data['volume']
        
        # Detectar volumen cero
        zero_volume = volume == 0
        zero_count = zero_volume.sum()
        
        if zero_count > 0:
            # Encontrar streaks de volumen cero
            zero_streaks = []
            streak_start = None
            streak_length = 0
            
            for idx, is_zero in zero_volume.items():
                if is_zero:
                    if streak_start is None:
                        streak_start = idx
                        streak_length = 1
                    else:
                        streak_length += 1
                else:
                    if streak_start is not None and streak_length > self.validation_thresholds['max_zero_volume_streak']:
                        anomalies.append({
                            'date': streak_start,
                            'type': 'zero_volume_streak',
                            'length': streak_length
                        })
                    streak_start = None
                    streak_length = 0
            
            # Check último streak
            if streak_start is not None and streak_length > self.validation_thresholds['max_zero_volume_streak']:
                anomalies.append({
                    'date': streak_start,
                    'type': 'zero_volume_streak', 
                    'length': streak_length
                })
        
        # Detectar volumen anómalamente alto
        if len(volume) > 20:
            vol_mean = volume.mean()
            vol_std = volume.std()
            high_volume_threshold = vol_mean + 3 * vol_std
            
            high_volume = volume > high_volume_threshold
            for idx in data.index[high_volume]:
                anomalies.append({
                    'date': idx,
                    'type': 'high_volume_spike',
                    'value': volume.loc[idx],
                    'threshold': high_volume_threshold
                })
        
        return {'anomalies': anomalies}
    
    def _calculate_quality_score(self, temporal: Dict, indicators: Dict, 
                               prices: Dict, volume: Dict) -> float:
        """Calcular score de calidad general (0-100)"""
        score = 100.0
        
        # Penalizar gaps temporales (40% del score)
        gap_penalty = min(temporal['gap_percentage'] * 2, 40)  # Máximo 40 puntos
        score -= gap_penalty
        
        # Penalizar indicadores con problemas (30% del score)
        total_indicators = 11  # Número de indicadores esperados
        problem_indicators = len(indicators['nan_indicators']) + len(indicators['inf_indicators'])
        indicator_penalty = (problem_indicators / total_indicators) * 30
        score -= indicator_penalty
        
        # Penalizar anomalías de precios (20% del score)
        price_anomalies = len(prices['anomalies'])
        if temporal['actual_periods'] > 0:
            price_penalty = min((price_anomalies / temporal['actual_periods']) * 100, 20)
            score -= price_penalty
        
        # Penalizar problemas de volumen (10% del score)
        volume_anomalies = len(volume['anomalies'])
        if temporal['actual_periods'] > 0:
            volume_penalty = min((volume_anomalies / temporal['actual_periods']) * 50, 10)
            score -= volume_penalty
        
        return max(0, score)
    
    def _determine_quality_level(self, score: float) -> DataQuality:
        """Determinar nivel de calidad basado en score"""
        if score >= 90:
            return DataQuality.EXCELLENT
        elif score >= 75:
            return DataQuality.GOOD
        elif score >= 60:
            return DataQuality.FAIR
        elif score >= 40:
            return DataQuality.POOR
        else:
            return DataQuality.UNUSABLE
    
    def _generate_warnings_and_recommendations(self, temporal: Dict, indicators: Dict,
                                             prices: Dict, volume: Dict) -> Tuple[List[str], List[str]]:
        """Generar warnings y recomendaciones"""
        warnings = []
        recommendations = []
        
        # Warnings temporales
        if temporal['gap_percentage'] > 5:
            warnings.append(f"Missing {temporal['gap_percentage']:.1f}% of expected data points")
        
        if temporal['largest_gap_days'] > 3:
            warnings.append(f"Largest data gap: {temporal['largest_gap_days']} days")
        
        # Warnings de indicadores
        if indicators['nan_indicators']:
            warnings.append(f"Indicators with NaN values: {', '.join(indicators['nan_indicators'])}")
        
        if indicators['inf_indicators']:
            warnings.append(f"Indicators with infinite values: {', '.join(indicators['inf_indicators'])}")
        
        # Warnings de precios
        price_jumps = [a for a in prices['anomalies'] if a['type'] == 'price_jump']
        if len(price_jumps) > 2:
            warnings.append(f"{len(price_jumps)} large price movements detected")
        
        # Recommendations
        if temporal['gap_percentage'] > 15:
            recommendations.append("Download more complete historical data")
        
        if indicators['nan_indicators'] or indicators['inf_indicators']:
            recommendations.append("Recalculate indicators with proper data cleaning")
        
        if len(price_jumps) > 3:
            recommendations.append("Review price data for stock splits or corporate actions")
        
        return warnings, recommendations

@dataclass 
class BacktestTrade:
    """Representa un trade completado en el backtest"""
    symbol: str
    direction: str
    entry_signal: TradingSignal
    entry_time: datetime
    entry_price: float
    position_size: float
    exit_time: datetime
    exit_price: float
    exit_reason: str
    pnl_dollars: float
    pnl_percent: float
    hold_time_hours: float
    max_favorable_excursion: float
    max_adverse_excursion: float
    
    # Nuevos campos de validación
    data_quality_score: float
    price_slippage: float
    execution_issues: List[str]

@dataclass
class BacktestMetrics:
    """Métricas completas del backtest con validación"""
    # Métricas básicas (mismo contenido que antes)
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    average_win: float
    average_loss: float
    profit_factor: float
    sharpe_ratio: float
    max_drawdown: float
    max_drawdown_duration: int
    buy_hold_return: float
    excess_return: float
    best_trade: float
    worst_trade: float
    avg_hold_time: float
    start_date: datetime
    end_date: datetime
    total_days: int
    
    # Nuevas métricas de validación
    data_quality_reports: Dict[str, DataValidationReport]
    avg_data_quality: float
    trades_on_poor_data: int
    reliability_score: float  # Confiabilidad general del backtest

class ValidatedBacktestEngine:
    """Motor de backtesting con validación robusta de datos"""
    
    def __init__(self, account_balance: float = 10000, strict_mode: bool = True):
        """
        Args:
            account_balance: Saldo inicial
            strict_mode: Si True, rechaza datos de calidad POOR/UNUSABLE
        """
        self.account_balance = account_balance
        self.initial_balance = account_balance
        self.strict_mode = strict_mode
        
        # Componentes
        self.scanner = SignalScanner()
        self.indicators_calc = TechnicalIndicators()
        self.position_calc = PositionCalculator()
        self.data_validator = DataValidator()
        
        # Estado del backtest
        self.trades: List[BacktestTrade] = []
        self.equity_curve: List[Tuple[datetime, float]] = []
        self.validation_reports: Dict[str, DataValidationReport] = {}
        
        # Configuración de trading
        self.max_positions = 5
        self.position_size_pct = 0.02
        self.commission = 0.001
        self.slippage_bps = 5  # 5 basis points de slippage
        
        logger.info(f"🚀 ValidatedBacktestEngine initialized - Strict mode: {strict_mode}")
    
    def get_historical_data(self, symbol: str = None, start_date: datetime = None, 
                           end_date: datetime = None) -> pd.DataFrame:
        """Obtener y validar datos históricos"""
        try:
            conn = get_connection()
            if not conn:
                raise Exception("No database connection available")
            
            query = """
            SELECT * FROM indicators_data
            WHERE 1=1
            """
            params = []
            
            if symbol:
                query += " AND symbol = ?"
                params.append(symbol)
            
            if start_date:
                query += " AND timestamp >= ?"
                params.append(start_date.isoformat())
            
            if end_date:
                query += " AND timestamp <= ?"
                params.append(end_date.isoformat())
            
            query += " ORDER BY timestamp ASC"
            
            df = pd.read_sql_query(query, conn, params=params)
            conn.close()
            
            if df.empty:
                return df
            
            # Convertir timestamp y establecer como índice
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp', inplace=True)
            
            return df
            
        except Exception as e:
            logger.error(f"❌ Error loading historical data: {e}")
            return pd.DataFrame()
    
    def validate_all_data(self, symbols: List[str], start_date: datetime, 
                         end_date: datetime) -> Dict[str, DataValidationReport]:
        """Validar datos de todos los símbolos antes del backtest"""
        logger.info(f"🔍 Validating data quality for {len(symbols)} symbols...")
        
        validation_reports = {}
        
        for symbol in symbols:
            # Cargar datos del símbolo
            data = self.get_historical_data(symbol, start_date, end_date)
            
            # Validar calidad
            report = self.data_validator.validate_symbol_data(
                symbol, data, start_date, end_date
            )
            
            validation_reports[symbol] = report
            
            # Log resultados
            quality_emoji = {
                DataQuality.EXCELLENT: "🟢",
                DataQuality.GOOD: "🔵", 
                DataQuality.FAIR: "🟡",
                DataQuality.POOR: "🟠",
                DataQuality.UNUSABLE: "🔴"
            }
            
            emoji = quality_emoji.get(report.overall_quality, "❓")
            logger.info(f"{emoji} {symbol}: {report.overall_quality.value} "
                       f"({report.quality_score:.1f}/100) - "
                       f"{report.gap_percentage:.1f}% gaps")
        
        # Resumen general
        usable_symbols = [s for s, r in validation_reports.items() if r.usable_for_backtest]
        avg_quality = np.mean([r.quality_score for r in validation_reports.values()])
        
        logger.info(f"📊 Data validation summary:")
        logger.info(f"   Total symbols: {len(symbols)}")
        logger.info(f"   Usable symbols: {len(usable_symbols)}")
        logger.info(f"   Average quality: {avg_quality:.1f}/100")
        
        if self.strict_mode:
            poor_symbols = [s for s, r in validation_reports.items() 
                           if r.overall_quality in [DataQuality.POOR, DataQuality.UNUSABLE]]
            if poor_symbols:
                logger.warning(f"⚠️ Strict mode: Excluding {len(poor_symbols)} symbols with poor data quality")
        
        return validation_reports
    
    def run_backtest(self, symbols: List[str] = None, start_date: datetime = None, 
                     end_date: datetime = None) -> BacktestMetrics:
        """Ejecutar backtest validado"""
        logger.info(f"🚀 Starting validated backtest...")
        
        # Defaults
        if not symbols:
            symbols = ['AAPL', 'MSFT', 'GOOGL']
        if not start_date:
            start_date = datetime.now() - timedelta(days=90)
        if not end_date:
            end_date = datetime.now()
        
        # PASO 1: Validación completa de datos
        self.validation_reports = self.validate_all_data(symbols, start_date, end_date)
        
        # PASO 2: Filtrar símbolos según calidad de datos
        if self.strict_mode:
            valid_symbols = [
                symbol for symbol, report in self.validation_reports.items()
                if report.usable_for_backtest and report.overall_quality not in [DataQuality.POOR, DataQuality.UNUSABLE]
            ]
        else:
            valid_symbols = [
                symbol for symbol, report in self.validation_reports.items()
                if report.usable_for_backtest
            ]
        
        if not valid_symbols:
            logger.error("❌ No symbols have sufficient data quality for backtesting")
            return self._create_empty_metrics(start_date, end_date)
        
        if len(valid_symbols) < len(symbols):
            excluded = set(symbols) - set(valid_symbols)
            logger.warning(f"⚠️ Excluding symbols due to data quality: {excluded}")
        
        logger.info(f"📊 Proceeding with {len(valid_symbols)} validated symbols: {valid_symbols}")
        
        # PASO 3: Ejecutar backtest solo con símbolos validados
        return self._execute_validated_backtest(valid_symbols, start_date, end_date)
    
    def _execute_validated_backtest(self, symbols: List[str], start_date: datetime, 
                                   end_date: datetime) -> BacktestMetrics:
        """Ejecutar backtest con datos ya validados"""
        # Reset estado
        self.trades.clear()
        self.equity_curve.clear()
        self.account_balance = self.initial_balance
        
        # Cargar datos validados
        all_data = {}
        for symbol in symbols:
            data = self.get_historical_data(symbol, start_date, end_date)
            if not data.empty:
                all_data[symbol] = data
        
        # Generar fechas de trading
        all_dates = set()
        for data in all_data.values():
            all_dates.update(data.index)
        all_dates = sorted(list(all_dates))
        
        logger.info(f"📅 Processing {len(all_dates)} validated trading periods...")
        
        # Simular trading con validación en cada paso
        for i, current_date in enumerate(all_dates[:-20]):
            self.equity_curve.append((current_date, self.account_balance))
            
            # Buscar señales
            for symbol in symbols:
                if symbol not in all_data:
                    continue
                
                # Verificar calidad de datos para esta fecha
                if not self._validate_date_data(symbol, current_date):
                    continue
                
                # Simular señal y trade con validación
                signal = self._simulate_validated_signal(symbol, all_data[symbol], current_date)
                
                if signal:
                    future_data = self._get_future_data(all_data[symbol], current_date, 20)
                    if len(future_data) > 5:  # Mínimo 5 períodos futuros
                        trade = self._simulate_validated_trade(signal, future_data)
                        if trade:
                            self.trades.append(trade)
        
        # Calcular métricas con información de validación
        return self._calculate_validated_metrics(start_date, end_date, symbols)
    
    def _validate_date_data(self, symbol: str, date: datetime) -> bool:
        """Validar que los datos para una fecha específica sean confiables"""
        if symbol not in self.validation_reports:
            return False
        
        report = self.validation_reports[symbol]
        
        # No tradear si la calidad general es muy baja
        if report.overall_quality == DataQuality.UNUSABLE:
            return False
        
        # No tradear en fechas cercanas a gaps grandes
        for gap in getattr(report, 'temporal_gaps', []):
            gap_start = gap.get('start')
            gap_end = gap.get('end')
            if gap_start and gap_end:
                # Evitar 2 días antes y después de gaps grandes
                if gap.get('days', 0) > 3:
                    if abs((date - gap_start).days) <= 2 or abs((date - gap_end).days) <= 2:
                        return False
        
        return True
    
    def _simulate_validated_signal(self, symbol: str, data: pd.DataFrame, 
                                  current_date: datetime) -> Optional[TradingSignal]:
        """Simular señal con validación de datos en tiempo real"""
        try:
            if current_date not in data.index:
                return None
            
            row = data.loc[current_date]
            
            # Validar que los indicadores para esta fecha sean válidos
            required_indicators = ['rsi_value', 'macd_histogram', 'vwap_value', 'close_price']
            for indicator in required_indicators:
                if indicator not in row or pd.isna(row[indicator]) or np.isinf(row[indicator]):
                    logger.debug(f"⚠️ {symbol} @ {current_date}: Invalid {indicator}")
                    return None
            
            # Validar rangos de indicadores
            if not (0 <= row.get('rsi_value', 50) <= 100):
                return None
            
            if row.get('close_price', 0) <= 0:
                return None
            
            # Reconstruir estructura de indicadores (código anterior...)
            indicators = {
                'symbol': symbol,
                'timestamp': current_date,
                'current_price': row['close_price'],
                'current_volume': row.get('volume', 0),
                
                'macd': {
                    'macd': row.get('macd_line', 0),
                    'signal': row.get('macd_signal', 0),
                    'histogram': row.get('macd_histogram', 0),
                    'bullish_cross': row.get('macd_histogram', 0) > 0,
                    'bearish_cross': row.get('macd_histogram', 0) < 0,
                    'signal_type': 'BULLISH' if row.get('macd_histogram', 0) > 0 else 'BEARISH',
                    'signal_strength': min(abs(row.get('macd_histogram', 0)) * 100, 20)
                },
                
                'rsi': {
                    'rsi': row.get('rsi_value', 50),
                    'oversold': row.get('rsi_value', 50) < 40,
                    'overbought': row.get('rsi_value', 50) > 60,
                    'signal_type': 'OVERSOLD' if row.get('rsi_value', 50) < 40 else 'OVERBOUGHT' if row.get('rsi_value', 50) > 60 else 'NEUTRAL',
                    'signal_strength': max(0, 20 - abs(row.get('rsi_value', 50) - 50)) if row.get('rsi_value', 50) < 40 or row.get('rsi_value', 50) > 60 else 0
                },
                
                'vwap': {
                    'vwap': row.get('vwap_value', row['close_price']),
                    'deviation_pct': row.get('vwap_deviation_pct', 0),
                    'signal_type': 'NEAR_VWAP' if abs(row.get('vwap_deviation_pct', 0)) <= 0.5 else 'ABOVE_VWAP' if row.get('vwap_deviation_pct', 0) > 0 else 'BELOW_VWAP',
                    'signal_strength': 15 if abs(row.get('vwap_deviation_pct', 0)) <= 0.5 else 10
                },
                
                'roc': {
                    'roc': row.get('roc_value', 0),
                    'bullish_momentum': row.get('roc_value', 0) > 1.5,
                    'bearish_momentum': row.get('roc_value', 0) < -1.5,
                    'signal_type': 'BULLISH' if row.get('roc_value', 0) > 1.5 else 'BEARISH' if row.get('roc_value', 0) < -1.5 else 'NEUTRAL',
                    'signal_strength': min(abs(row.get('roc_value', 0)) * 2, 15)
                },
                
                'bollinger': {
                    'upper_band': row.get('bb_upper', 0),
                    'middle_band': row.get('bb_middle', row['close_price']),
                    'lower_band': row.get('bb_lower', 0),
                    'bb_position': row.get('bb_position', 0.5),
                    'near_lower': row.get('bb_position', 0.5) < 0.2,
                    'near_upper': row.get('bb_position', 0.5) > 0.8,
                    'signal_type': 'LOWER_BAND' if row.get('bb_position', 0.5) < 0.2 else 'UPPER_BAND' if row.get('bb_position', 0.5) > 0.8 else 'NEUTRAL',
                    'signal_strength': 15 if row.get('bb_position', 0.5) < 0.2 or row.get('bb_position', 0.5) > 0.8 else 0
                },
                
                'volume_osc': {
                    'volume_oscillator': row.get('volume_oscillator', 0),
                    'high_volume': row.get('volume_oscillator', 0) > 50,
                    'signal_type': 'HIGH_VOLUME' if row.get('volume_oscillator', 0) > 50 else 'NORMAL',
                    'signal_strength': 10 if row.get('volume_oscillator', 0) > 50 else 0
                },
                
                'atr': {
                    'atr': row.get('atr_value', 0),
                    'atr_percentage': row.get('atr_percentage', 0),
                    'volatility_level': row.get('volatility_level', 'NORMAL')
                }
            }
            
            # Usar scanner para evaluar señal
            signal = self.scanner.evaluate_signal_from_indicators(indicators, current_date)
            
            if signal and signal.signal_strength >= config.SIGNAL_THRESHOLDS['NO_TRADE']:
                return signal
            
            return None
            
        except Exception as e:
            logger.debug(f"❌ Error simulating signal for {symbol} @ {current_date}: {e}")
            return None
    
    def _get_future_data(self, data: pd.DataFrame, current_date: datetime, periods: int) -> pd.DataFrame:
        """Obtener datos futuros validados"""
        try:
            current_idx = data.index.get_loc(current_date)
            end_idx = min(current_idx + periods, len(data))
            future_data = data.iloc[current_idx+1:end_idx]
            
            # Validar continuidad de datos futuros
            if len(future_data) < periods * 0.7:  # Mínimo 70% de datos esperados
                logger.debug(f"⚠️ Insufficient future data: {len(future_data)}/{periods}")
            
            return future_data
            
        except Exception as e:
            logger.debug(f"❌ Error getting future data: {e}")
            return pd.DataFrame()
    
    def _simulate_validated_trade(self, signal: TradingSignal, future_data: pd.DataFrame) -> Optional[BacktestTrade]:
        """Simular trade con validación y slippage realista"""
        try:
            # Calcular tamaño de posición
            position_size = self._calculate_position_size(signal)
            if position_size <= 0:
                return None
            
            # Aplicar slippage realista en entrada
            entry_slippage = self._calculate_slippage(signal.current_price, signal.current_volume)
            entry_price = signal.current_price * (1 + entry_slippage if signal.signal_type == "LONG" else 1 - entry_slippage)
            
            # Definir niveles de salida
            stop_loss_pct = 0.02
            take_profit_pct = 0.04
            max_hold_periods = 5
            
            if signal.signal_type == "LONG":
                stop_loss = entry_price * (1 - stop_loss_pct)
                take_profit = entry_price * (1 + take_profit_pct)
            else:  # SHORT
                stop_loss = entry_price * (1 + stop_loss_pct)
                take_profit = entry_price * (1 - take_profit_pct)
            
            # Simular evolución del trade con validación continua
            data_quality_score = self.validation_reports[signal.symbol].quality_score
            execution_issues = []
            
            max_favorable = 0.0
            max_adverse = 0.0
            
            for i, (idx, row) in enumerate(future_data.iterrows()):
                # Validar calidad de datos para este período
                if pd.isna(row['close_price']) or row['close_price'] <= 0:
                    execution_issues.append(f"Invalid price data @ {idx}")
                    continue
                
                # Detectar gaps de precio
                if i > 0:
                    prev_price = future_data.iloc[i-1]['close_price']
                    price_change = abs(row['close_price'] - prev_price) / prev_price
                    if price_change > 0.1:  # Gap >10%
                        execution_issues.append(f"Price gap {price_change:.1%} @ {idx}")
                
                current_price = row['close_price']
                
                # Calcular MFE y MAE
                if signal.signal_type == "LONG":
                    unrealized_pct = (current_price - entry_price) / entry_price
                    max_favorable = max(max_favorable, unrealized_pct)
                    max_adverse = min(max_adverse, unrealized_pct)
                    
                    # Check exit conditions con slippage
                    if current_price <= stop_loss:
                        exit_slippage = self._calculate_slippage(stop_loss, row.get('volume', 0))
                        exit_price = stop_loss * (1 - exit_slippage)  # Slippage negativo en stop loss
                        exit_reason = "STOP_LOSS"
                        exit_time = idx
                        break
                    elif current_price >= take_profit:
                        exit_slippage = self._calculate_slippage(take_profit, row.get('volume', 0))
                        exit_price = take_profit * (1 - exit_slippage)  # Slippage negativo en take profit
                        exit_reason = "TAKE_PROFIT"
                        exit_time = idx
                        break
                        
                else:  # SHORT
                    unrealized_pct = (entry_price - current_price) / entry_price
                    max_favorable = max(max_favorable, unrealized_pct)
                    max_adverse = min(max_adverse, unrealized_pct)
                    
                    if current_price >= stop_loss:
                        exit_slippage = self._calculate_slippage(stop_loss, row.get('volume', 0))
                        exit_price = stop_loss * (1 + exit_slippage)  # Slippage positivo en stop loss SHORT
                        exit_reason = "STOP_LOSS"
                        exit_time = idx
                        break
                    elif current_price <= take_profit:
                        exit_slippage = self._calculate_slippage(take_profit, row.get('volume', 0))
                        exit_price = take_profit * (1 + exit_slippage)  # Slippage positivo en take profit SHORT
                        exit_reason = "TAKE_PROFIT"
                        exit_time = idx
                        break
                
                # Límite de tiempo
                if i >= max_hold_periods:
                    exit_slippage = self._calculate_slippage(current_price, row.get('volume', 0))
                    exit_price = current_price * (1 - exit_slippage if signal.signal_type == "LONG" else 1 + exit_slippage)
                    exit_reason = "TIME_LIMIT"
                    exit_time = idx
                    break
            else:
                # Salir al final de los datos
                final_row = future_data.iloc[-1]
                exit_slippage = self._calculate_slippage(final_row['close_price'], final_row.get('volume', 0))
                exit_price = final_row['close_price'] * (1 - exit_slippage if signal.signal_type == "LONG" else 1 + exit_slippage)
                exit_reason = "END_OF_DATA"
                exit_time = future_data.index[-1]
            
            # Calcular resultados con comisiones
            if signal.signal_type == "LONG":
                pnl_pct = (exit_price - entry_price) / entry_price
                pnl_dollars = position_size * (exit_price - entry_price)
            else:  # SHORT
                pnl_pct = (entry_price - exit_price) / entry_price
                pnl_dollars = position_size * (entry_price - exit_price)
            
            # Aplicar comisiones
            position_value = position_size * entry_price
            commission_cost = position_value * self.commission * 2  # Entry + exit
            pnl_dollars -= commission_cost
            
            # Tiempo de retención
            hold_time_hours = (exit_time - signal.timestamp).total_seconds() / 3600
            
            # Calcular slippage total
            total_slippage = entry_slippage + exit_slippage
            
            trade = BacktestTrade(
                symbol=signal.symbol,
                direction=signal.signal_type,
                entry_signal=signal,
                entry_time=signal.timestamp,
                entry_price=entry_price,
                position_size=position_size,
                exit_time=exit_time,
                exit_price=exit_price,
                exit_reason=exit_reason,
                pnl_dollars=pnl_dollars,
                pnl_percent=pnl_pct,
                hold_time_hours=hold_time_hours,
                max_favorable_excursion=max_favorable,
                max_adverse_excursion=max_adverse,
                data_quality_score=data_quality_score,
                price_slippage=total_slippage,
                execution_issues=execution_issues
            )
            
            # Actualizar balance
            self.account_balance += pnl_dollars
            
            logger.debug(f"✅ Validated trade: {signal.symbol} {signal.signal_type} "
                        f"PnL: ${pnl_dollars:.2f} Quality: {data_quality_score:.1f}")
            
            return trade
            
        except Exception as e:
            logger.error(f"❌ Error in validated trade simulation: {e}")
            return None
    
    def _calculate_position_size(self, signal: TradingSignal) -> float:
        """Calcular tamaño de posición (igual que antes)"""
        try:
            if signal.position_plan:
                risk_amount = self.account_balance * signal.position_plan.total_risk_percent / 100
            else:
                risk_amount = self.account_balance * self.position_size_pct
            
            shares = risk_amount / signal.current_price
            max_position_value = self.account_balance * 0.1
            max_shares = max_position_value / signal.current_price
            
            return min(shares, max_shares)
            
        except Exception:
            return 0
    
    def _calculate_slippage(self, price: float, volume: float) -> float:
        """Calcular slippage realista basado en volumen"""
        try:
            base_slippage = self.slippage_bps / 10000  # Convertir basis points a decimal
            
            # Penalizar volumen bajo
            if volume < 100000:  # Volumen muy bajo
                slippage_multiplier = 2.0
            elif volume < 500000:  # Volumen bajo
                slippage_multiplier = 1.5
            else:  # Volumen normal/alto
                slippage_multiplier = 1.0
            
            return base_slippage * slippage_multiplier
            
        except Exception:
            return self.slippage_bps / 10000
    
    def _calculate_validated_metrics(self, start_date: datetime, end_date: datetime, 
                                   symbols: List[str]) -> BacktestMetrics:
        """Calcular métricas incluyendo información de validación"""
        
        # Métricas básicas (reutilizar código anterior)
        if not self.trades:
            return self._create_empty_metrics(start_date, end_date)
        
        # Calcular métricas estándar
        total_trades = len(self.trades)
        winning_trades = len([t for t in self.trades if t.pnl_dollars > 0])
        losing_trades = total_trades - winning_trades
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        total_pnl = sum(t.pnl_dollars for t in self.trades)
        wins = [t.pnl_dollars for t in self.trades if t.pnl_dollars > 0]
        losses = [t.pnl_dollars for t in self.trades if t.pnl_dollars < 0]
        
        average_win = np.mean(wins) if wins else 0
        average_loss = np.mean(losses) if losses else 0
        
        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        # Calcular métricas adicionales de validación
        avg_data_quality = np.mean([r.quality_score for r in self.validation_reports.values()])
        trades_on_poor_data = len([t for t in self.trades if t.data_quality_score < 60])
        
        # Score de confiabilidad del backtest
        quality_penalty = max(0, (75 - avg_data_quality) / 75)  # Penalizar si calidad < 75
        execution_penalty = trades_on_poor_data / total_trades if total_trades > 0 else 0
        reliability_score = (1 - quality_penalty - execution_penalty) * 100
        
        # Drawdown y Sharpe (simplificados)
        equity_values = [eq[1] for eq in self.equity_curve]
        if equity_values:
            running_max = np.maximum.accumulate(equity_values)
            drawdowns = (equity_values - running_max) / running_max
            max_drawdown = min(drawdowns) if len(drawdowns) > 0 else 0
        else:
            max_drawdown = 0
        
        # Sharpe ratio simplificado
        if len(self.equity_curve) > 1:
            returns = []
            for i in range(1, len(self.equity_curve)):
                prev_balance = self.equity_curve[i-1][1]
                curr_balance = self.equity_curve[i][1]
                ret = (curr_balance - prev_balance) / prev_balance if prev_balance > 0 else 0
                returns.append(ret)
            
            if returns:
                avg_return = np.mean(returns)
                return_std = np.std(returns)
                sharpe_ratio = (avg_return / return_std * np.sqrt(252)) if return_std > 0 else 0
            else:
                sharpe_ratio = 0
        else:
            sharpe_ratio = 0
        
        # Buy & hold
        buy_hold_return = self._calculate_buy_hold_return(symbols[0] if symbols else 'SPY', start_date, end_date)
        strategy_return = (self.account_balance - self.initial_balance) / self.initial_balance
        excess_return = strategy_return - buy_hold_return
        
        # Trade distribution
        trade_returns = [t.pnl_dollars for t in self.trades]
        best_trade = max(trade_returns) if trade_returns else 0
        worst_trade = min(trade_returns) if trade_returns else 0
        avg_hold_time = np.mean([t.hold_time_hours for t in self.trades]) if self.trades else 0
        
        return BacktestMetrics(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            total_pnl=total_pnl,
            average_win=average_win,
            average_loss=average_loss,
            profit_factor=profit_factor,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            max_drawdown_duration=0,  # Simplificado
            buy_hold_return=buy_hold_return,
            excess_return=excess_return,
            best_trade=best_trade,
            worst_trade=worst_trade,
            avg_hold_time=avg_hold_time,
            start_date=start_date,
            end_date=end_date,
            total_days=(end_date - start_date).days,
            
            # Métricas de validación
            data_quality_reports=self.validation_reports,
            avg_data_quality=avg_data_quality,
            trades_on_poor_data=trades_on_poor_data,
            reliability_score=reliability_score
        )
    
    def _calculate_buy_hold_return(self, symbol: str, start_date: datetime, end_date: datetime) -> float:
        """Calcular Buy & Hold return"""
        try:
            data = self.get_historical_data(symbol, start_date, end_date)
            if len(data) < 2:
                return 0.0
            
            start_price = data.iloc[0]['close_price']
            end_price = data.iloc[-1]['close_price']
            
            return (end_price - start_price) / start_price
            
        except Exception:
            return 0.0
    
    def _create_empty_metrics(self, start_date: datetime, end_date: datetime) -> BacktestMetrics:
        """Crear métricas vacías"""
        return BacktestMetrics(
            total_trades=0, winning_trades=0, losing_trades=0, win_rate=0.0,
            total_pnl=0.0, average_win=0.0, average_loss=0.0, profit_factor=0.0,
            sharpe_ratio=0.0, max_drawdown=0.0, max_drawdown_duration=0,
            buy_hold_return=0.0, excess_return=0.0, best_trade=0.0, worst_trade=0.0,
            avg_hold_time=0.0, start_date=start_date, end_date=end_date,
            total_days=(end_date - start_date).days,
            data_quality_reports=self.validation_reports,
            avg_data_quality=0.0, trades_on_poor_data=0, reliability_score=0.0
        )
    
    def print_validation_summary(self):
        """Imprimir resumen de validación de datos"""
        if not self.validation_reports:
            print("No validation data available")
            return
        
        print("=" * 60)
        print("🔍 DATA VALIDATION SUMMARY")
        print("=" * 60)
        
        quality_counts = {q: 0 for q in DataQuality}
        for report in self.validation_reports.values():
            quality_counts[report.overall_quality] += 1
        
        print(f"📊 Data Quality Distribution:")
        for quality, count in quality_counts.items():
            if count > 0:
                emoji = {"EXCELLENT": "🟢", "GOOD": "🔵", "FAIR": "🟡", "POOR": "🟠", "UNUSABLE": "🔴"}
                print(f"   {emoji.get(quality.value, '❓')} {quality.value}: {count} symbols")
        
        avg_quality = np.mean([r.quality_score for r in self.validation_reports.values()])
        print(f"\n📈 Average Data Quality: {avg_quality:.1f}/100")
        
        # Top issues
        all_warnings = []
        for report in self.validation_reports.values():
            all_warnings.extend(report.warnings)
        
        if all_warnings:
            from collections import Counter
            common_issues = Counter(all_warnings).most_common(5)
            print(f"\n⚠️ Most Common Issues:")
            for issue, count in common_issues:
                print(f"   • {issue} ({count} symbols)")
    
    def print_summary(self, metrics: BacktestMetrics):
        """Imprimir resumen completo incluyendo validación"""
        print("=" * 60)
        print("📊 VALIDATED BACKTEST SUMMARY")
        print("=" * 60)
        
        # Información de validación
        print(f"🔍 DATA QUALITY:")
        print(f"   Average Quality Score: {metrics.avg_data_quality:.1f}/100")
        print(f"   Reliability Score: {metrics.reliability_score:.1f}/100")
        print(f"   Trades on Poor Data: {metrics.trades_on_poor_data}/{metrics.total_trades}")
        print()
        
        # Métricas estándar
        print(f"📅 Period: {metrics.start_date.strftime('%Y-%m-%d')} to {metrics.end_date.strftime('%Y-%m-%d')} ({metrics.total_days} days)")
        print(f"💰 Initial Balance: ${self.initial_balance:,.2f}")
        print(f"💰 Final Balance: ${self.account_balance:,.2f}")
        
        total_return = (self.account_balance - self.initial_balance) / self.initial_balance
        print(f"📈 Total Return: {total_return:.2%}")
        print(f"📊 Buy & Hold: {metrics.buy_hold_return:.2%}")
        print(f"⚡ Excess Return: {metrics.excess_return:+.2%}")
        print()
        
        print("🎯 TRADE STATISTICS:")
        print(f"   Total Trades: {metrics.total_trades}")
        print(f"   Win Rate: {metrics.win_rate:.1%} ({metrics.winning_trades}W / {metrics.losing_trades}L)")
        print(f"   Profit Factor: {metrics.profit_factor:.2f}")
        print(f"   Average Win: ${metrics.average_win:,.2f}")
        print(f"   Average Loss: ${metrics.average_loss:,.2f}")
        print(f"   Best Trade: ${metrics.best_trade:,.2f}")
        print(f"   Worst Trade: ${metrics.worst_trade:,.2f}")
        print()
        
        print("📉 RISK METRICS:")
        print(f"   Sharpe Ratio: {metrics.sharpe_ratio:.2f}")
        print(f"   Max Drawdown: {metrics.max_drawdown:.2%}")
        print(f"   Avg Hold Time: {metrics.avg_hold_time:.1f} hours")
        print()
        
        # Interpretación con consideración de calidad de datos
        print("🎯 RELIABILITY ASSESSMENT:")
        
        if metrics.reliability_score >= 80:
            print("   ✅ High reliability - Results are trustworthy")
        elif metrics.reliability_score >= 60:
            print("   ⚡ Moderate reliability - Results should be interpreted with caution")
        else:
            print("   ❌ Low reliability - Results may not be representative")
        
        if metrics.avg_data_quality < 60:
            print("   ⚠️ Poor data quality detected - Consider getting better historical data")
        
        if metrics.trades_on_poor_data > metrics.total_trades * 0.2:
            print("   ⚠️ High percentage of trades executed on poor quality data")

def main():
    """Función principal CLI con validación"""
    parser = argparse.ArgumentParser(description='Validated Backtest Engine V5.0')
    parser.add_argument('--symbols', nargs='+', default=['AAPL', 'MSFT', 'GOOGL'], 
                       help='Símbolos a testear')
    parser.add_argument('--start-date', help='Fecha de inicio (YYYY-MM-DD)')
    parser.add_argument('--end-date', help='Fecha de fin (YYYY-MM-DD)')
    parser.add_argument('--balance', type=float, default=10000, 
                       help='Saldo inicial de la cuenta')
    parser.add_argument('--strict', action='store_true', 
                       help='Modo estricto: rechazar datos de baja calidad')
    parser.add_argument('--validation-only', action='store_true',
                       help='Solo validar datos, no ejecutar backtest')
    parser.add_argument('--quick', action='store_true', 
                       help='Test rápido con configuración limitada')
    
    args = parser.parse_args()
    
    # Configurar parámetros
    symbols = args.symbols
    balance = args.balance
    strict_mode = args.strict
    
    # Parse dates
    start_date = None
    end_date = None
    
    if args.start_date:
        start_date = datetime.strptime(args.start_date, '%Y-%m-%d')
    if args.end_date:
        end_date = datetime.strptime(args.end_date, '%Y-%m-%d')
    
    # Quick test configuration
    if args.quick:
        symbols = symbols[:1]
        if not start_date:
            start_date = datetime.now() - timedelta(days=30)
        if not end_date:
            end_date = datetime.now()
        print("⚡ QUICK TEST MODE: Limited symbols and time period")
    else:
        if not start_date:
            start_date = datetime.now() - timedelta(days=90)
        if not end_date:
            end_date = datetime.now()
    
    print(f"🚀 VALIDATED BACKTEST ENGINE V5.0")
    print("=" * 50)
    print(f"🔍 Data Validation: {'STRICT' if strict_mode else 'PERMISSIVE'} mode")
    
    # Crear engine
    engine = ValidatedBacktestEngine(account_balance=balance, strict_mode=strict_mode)
    
    try:
        if args.validation_only:
            # Solo validación de datos
            print(f"🔍 VALIDATION-ONLY MODE")
            validation_reports = engine.validate_all_data(symbols, start_date, end_date)
            engine.print_validation_summary()
            
            # Mostrar detalles por símbolo
            print(f"\n📋 DETAILED VALIDATION RESULTS:")
            print("-" * 60)
            
            for symbol, report in validation_reports.items():
                quality_emoji = {
                    DataQuality.EXCELLENT: "🟢",
                    DataQuality.GOOD: "🔵", 
                    DataQuality.FAIR: "🟡",
                    DataQuality.POOR: "🟠",
                    DataQuality.UNUSABLE: "🔴"
                }
                
                emoji = quality_emoji.get(report.overall_quality, "❓")
                print(f"{emoji} {symbol}:")
                print(f"   Quality: {report.overall_quality.value} ({report.quality_score:.1f}/100)")
                print(f"   Data Coverage: {report.actual_periods}/{report.total_expected_periods} periods ({100-report.gap_percentage:.1f}%)")
                print(f"   Largest Gap: {report.largest_gap_days} days")
                print(f"   Price Anomalies: {len(report.price_anomalies)}")
                print(f"   Usable for Backtest: {'✅ Yes' if report.usable_for_backtest else '❌ No'}")
                
                if report.warnings:
                    print(f"   ⚠️ Warnings: {len(report.warnings)}")
                    for warning in report.warnings[:3]:  # Show first 3 warnings
                        print(f"      • {warning}")
                    if len(report.warnings) > 3:
                        print(f"      ... and {len(report.warnings) - 3} more")
                        
                if report.recommendations:
                    print(f"   💡 Recommendations:")
                    for rec in report.recommendations[:2]:  # Show first 2 recommendations
                        print(f"      • {rec}")
                print()
            
        else:
            # Backtest completo con validación
            metrics = engine.run_backtest(
                symbols=symbols,
                start_date=start_date,
                end_date=end_date
            )
            
            # Mostrar validación primero
            engine.print_validation_summary()
            print()
            
            # Mostrar resultados del backtest
            engine.print_summary(metrics)
            
            # Recomendaciones finales
            print(f"\n💡 RECOMMENDATIONS:")
            
            if metrics.reliability_score < 60:
                print("   🔴 CRITICAL: Low reliability score - results may not be trustworthy")
                print("      → Download more complete historical data")
                print("      → Use --strict mode to exclude poor quality data")
                print("      → Consider shorter time period with better data coverage")
            
            elif metrics.reliability_score < 80:
                print("   🟡 CAUTION: Moderate reliability - interpret results carefully")
                print("      → Some data quality issues detected")
                print("      → Consider validating key trades manually")
            
            else:
                print("   ✅ HIGH RELIABILITY: Results are trustworthy")
                
            if metrics.total_trades == 0:
                print("   📊 No trades executed - possible causes:")
                print("      → Signal thresholds too strict")
                print("      → Insufficient historical data")
                print("      → All symbols excluded due to data quality")
                print("      → Run with --validation-only to check data availability")
                
            elif metrics.total_trades < 10:
                print("   📊 Limited trades - consider:")
                print("      → Longer time period")
                print("      → More symbols")
                print("      → Lower signal thresholds")
                
            else:
                print("   📊 Good trade sample size for statistical significance")
                
            # Data quality specific recommendations
            if metrics.avg_data_quality < 70:
                print("   📈 Data Quality Improvements:")
                print("      → Download more recent data with python downloader.py")
                print("      → Check for missing trading days or holidays")
                print("      → Verify indicator calculations are correct")
            
            print(f"\n🎉 Validated backtest completed!")
            
    except KeyboardInterrupt:
        print("\n🛑 Backtest interrupted by user")
    except Exception as e:
        logger.error(f"❌ Backtest failed: {e}")
        print(f"❌ Error: {e}")
        print("💡 Troubleshooting steps:")
        print("   1. Make sure historical data is available (run populate_db.py)")
        print("   2. Check database connection")
        print("   3. Verify symbols have sufficient data coverage")
        print("   4. Try --validation-only to check data quality first")

if __name__ == "__main__":
    main()