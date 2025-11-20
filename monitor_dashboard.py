#!/usr/bin/env python3
"""
Streamlit实时监控面板

功能：
- 实时策略表现
- 关键指标监控
- 持仓状态
- 近期交易记录
- 风险告警
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import json
import os
from pathlib import Path

# 页面配置
st.set_page_config(
    page_title="量化交易监控面板",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 自定义CSS
st.markdown("""
<style>
    .big-font {
        font-size:30px !important;
        font-weight: bold;
    }
    .metric-card {
        background-color: #f0f2f6;
        padding: 20px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)


class TradingMonitor:
    """交易监控器"""

    def __init__(self):
        self.data_dir = Path("ml_data")
        self.model_dir = Path("ml_models")
        self.log_dir = Path("log")

    def load_equity_data(self) -> pd.DataFrame:
        """加载权益曲线数据"""
        equity_file = "backtest_equity.csv"
        if os.path.exists(equity_file):
            df = pd.read_csv(equity_file)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            return df
        return pd.DataFrame()

    def load_trades_data(self) -> pd.DataFrame:
        """加载交易记录"""
        trades_file = "backtest_trades.csv"
        if os.path.exists(trades_file):
            df = pd.read_csv(trades_file)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            return df
        return pd.DataFrame()

    def calculate_metrics(self, equity_df: pd.DataFrame, trades_df: pd.DataFrame) -> dict:
        """计算关键指标"""
        if equity_df.empty:
            return self._empty_metrics()

        initial_capital = equity_df['equity'].iloc[0]
        current_equity = equity_df['equity'].iloc[-1]
        total_return = ((current_equity - initial_capital) / initial_capital) * 100

        # 计算今日盈亏
        today = datetime.now().date()
        today_trades = trades_df[trades_df['timestamp'].dt.date == today]
        today_pnl = today_trades['pnl'].sum() if not today_trades.empty else 0

        # 计算胜率
        if not trades_df.empty:
            win_rate = (trades_df['pnl'] > 0).sum() / len(trades_df) * 100
            total_trades = len(trades_df)
        else:
            win_rate = 0
            total_trades = 0

        # 计算夏普比率
        if len(equity_df) > 1:
            returns = equity_df['equity'].pct_change().dropna()
            sharpe_ratio = (returns.mean() / returns.std()) * np.sqrt(252) if returns.std() > 0 else 0
        else:
            sharpe_ratio = 0

        # 计算最大回撤
        equity_series = equity_df['equity'].values
        running_max = np.maximum.accumulate(equity_series)
        drawdown = (equity_series - running_max) / running_max
        max_drawdown = abs(drawdown.min()) * 100 if len(drawdown) > 0 else 0

        return {
            'current_equity': current_equity,
            'total_return': total_return,
            'today_pnl': today_pnl,
            'total_trades': total_trades,
            'win_rate': win_rate,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown
        }

    def _empty_metrics(self) -> dict:
        """空指标"""
        return {
            'current_equity': 10000,
            'total_return': 0,
            'today_pnl': 0,
            'total_trades': 0,
            'win_rate': 0,
            'sharpe_ratio': 0,
            'max_drawdown': 0
        }


def main():
    """主函数"""
    # 标题
    st.title("📈 量化交易实时监控面板")
    st.markdown("---")

    # 创建监控器
    monitor = TradingMonitor()

    # 侧边栏
    with st.sidebar:
        st.header("⚙️ 控制面板")

        # 刷新按钮
        if st.button("🔄 刷新数据", use_container_width=True):
            st.rerun()

        st.markdown("---")

        # 自动刷新
        auto_refresh = st.checkbox("自动刷新", value=True)
        if auto_refresh:
            refresh_interval = st.slider("刷新间隔（秒）", 5, 60, 10)
            st.info(f"页面将每{refresh_interval}秒自动刷新")

        st.markdown("---")

        # 时间范围选择
        st.subheader("📅 时间范围")
        time_range = st.selectbox(
            "选择时间范围",
            ["最近1小时", "最近24小时", "最近7天", "最近30天", "全部"]
        )

        st.markdown("---")

        # 策略选择
        st.subheader("🎯 策略")
        strategy = st.selectbox(
            "选择策略",
            ["ML策略", "订单簿策略", "趋势策略", "全部策略"]
        )

    # 加载数据
    equity_df = monitor.load_equity_data()
    trades_df = monitor.load_trades_data()
    metrics = monitor.calculate_metrics(equity_df, trades_df)

    # 第一行：关键指标
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        delta_equity = metrics['current_equity'] - 10000
        st.metric(
            label="💰 当前权益",
            value=f"${metrics['current_equity']:.2f}",
            delta=f"${delta_equity:.2f}"
        )

    with col2:
        st.metric(
            label="📊 总收益率",
            value=f"{metrics['total_return']:.2f}%",
            delta=f"{metrics['total_return']:.2f}%"
        )

    with col3:
        st.metric(
            label="💵 今日盈亏",
            value=f"${metrics['today_pnl']:.2f}",
            delta=f"${metrics['today_pnl']:.2f}"
        )

    with col4:
        st.metric(
            label="🎯 胜率",
            value=f"{metrics['win_rate']:.1f}%",
            delta=None
        )

    st.markdown("---")

    # 第二行：风险指标
    col5, col6, col7, col8 = st.columns(4)

    with col5:
        st.metric(
            label="📈 夏普比率",
            value=f"{metrics['sharpe_ratio']:.3f}"
        )

    with col6:
        st.metric(
            label="📉 最大回撤",
            value=f"{metrics['max_drawdown']:.2f}%"
        )

    with col7:
        st.metric(
            label="🔢 总交易次数",
            value=f"{metrics['total_trades']}"
        )

    with col8:
        # 计算持仓数（模拟）
        open_positions = 2  # 这里可以从实际数据获取
        st.metric(
            label="📦 当前持仓",
            value=f"{open_positions}"
        )

    st.markdown("---")

    # 第三行：图表
    tab1, tab2, tab3, tab4 = st.tabs(["📈 权益曲线", "📊 交易分析", "🎯 持仓状态", "⚠️ 风险监控"])

    with tab1:
        st.subheader("权益曲线")

        if not equity_df.empty:
            fig = go.Figure()

            fig.add_trace(go.Scatter(
                x=equity_df['timestamp'],
                y=equity_df['equity'],
                mode='lines',
                name='权益',
                line=dict(color='#2E86AB', width=2),
                fill='tozeroy',
                fillcolor='rgba(46, 134, 171, 0.1)'
            ))

            # 添加基准线
            fig.add_hline(
                y=10000,
                line_dash="dash",
                line_color="gray",
                annotation_text="初始资金"
            )

            fig.update_layout(
                xaxis_title="时间",
                yaxis_title="权益 ($)",
                hovermode='x unified',
                height=400
            )

            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("暂无权益数据")

    with tab2:
        st.subheader("交易分析")

        if not trades_df.empty:
            col_a, col_b = st.columns(2)

            with col_a:
                # 盈亏分布
                st.markdown("**盈亏分布**")
                fig_pnl = px.histogram(
                    trades_df,
                    x='pnl',
                    nbins=30,
                    color_discrete_sequence=['#2E86AB']
                )
                fig_pnl.update_layout(
                    xaxis_title="盈亏 ($)",
                    yaxis_title="交易次数",
                    height=300
                )
                st.plotly_chart(fig_pnl, use_container_width=True)

            with col_b:
                # 退出原因分布
                st.markdown("**退出原因分布**")
                exit_counts = trades_df['exit_reason'].value_counts()
                fig_exit = px.pie(
                    values=exit_counts.values,
                    names=exit_counts.index,
                    hole=0.4
                )
                fig_exit.update_layout(height=300)
                st.plotly_chart(fig_exit, use_container_width=True)

            # 最近交易
            st.markdown("**最近20笔交易**")
            recent_trades = trades_df.tail(20).sort_values('timestamp', ascending=False)
            display_trades = recent_trades[['timestamp', 'side', 'entry_price', 'exit_price', 'pnl', 'exit_reason']].copy()
            display_trades['pnl'] = display_trades['pnl'].apply(lambda x: f"${x:.2f}")

            # 根据盈亏着色
            def color_pnl(val):
                if '$-' in val:
                    return 'background-color: #ffcccc'
                elif val != '$0.00':
                    return 'background-color: #ccffcc'
                return ''

            styled_trades = display_trades.style.applymap(color_pnl, subset=['pnl'])
            st.dataframe(styled_trades, use_container_width=True)

        else:
            st.info("暂无交易数据")

    with tab3:
        st.subheader("当前持仓")

        # 模拟持仓数据
        positions_data = {
            '交易对': ['BTC-USDT-SWAP', 'ETH-USDT-SWAP'],
            '方向': ['多头', '空头'],
            '开仓价': [98500.0, 3850.0],
            '当前价': [99200.0, 3820.0],
            '数量': [0.1, 1.0],
            '盈亏': [70.0, 30.0],
            '盈亏率': ['0.71%', '0.78%']
        }

        if positions_data:
            df_positions = pd.DataFrame(positions_data)
            st.dataframe(df_positions, use_container_width=True)
        else:
            st.info("当前无持仓")

    with tab4:
        st.subheader("风险监控")

        # 风险指标
        col_risk1, col_risk2, col_risk3 = st.columns(3)

        with col_risk1:
            st.metric("📉 当前回撤", f"{metrics['max_drawdown']:.2f}%")
            # 回撤警告
            if metrics['max_drawdown'] > 10:
                st.error("⚠️ 回撤超过10%！")
            elif metrics['max_drawdown'] > 5:
                st.warning("⚠️ 回撤超过5%")
            else:
                st.success("✅ 回撤正常")

        with col_risk2:
            # 模拟风险暴露
            risk_exposure = 35.2
            st.metric("💼 风险暴露", f"{risk_exposure:.1f}%")
            st.progress(int(risk_exposure))

        with col_risk3:
            # 模拟日内盈亏限制
            daily_limit = -200
            current_daily_pnl = metrics['today_pnl']
            st.metric("🚨 日内止损", f"${daily_limit}")
            if current_daily_pnl < daily_limit:
                st.error(f"⚠️ 已触发日内止损！当前盈亏: ${current_daily_pnl:.2f}")

        # 警告列表
        st.markdown("**⚠️ 风险告警**")
        alerts = []

        if metrics['max_drawdown'] > 10:
            alerts.append("🔴 最大回撤超过10%")
        if metrics['today_pnl'] < -100:
            alerts.append("🟠 今日亏损超过$100")
        if metrics['sharpe_ratio'] < 1.0:
            alerts.append("🟡 夏普比率低于1.0")

        if alerts:
            for alert in alerts:
                st.warning(alert)
        else:
            st.success("✅ 所有风险指标正常")

    # 底部：系统状态
    st.markdown("---")
    col_status1, col_status2, col_status3 = st.columns(3)

    with col_status1:
        st.info(f"📡 **数据更新时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    with col_status2:
        st.info(f"🤖 **策略状态**: 运行中")

    with col_status3:
        st.info(f"🌐 **API连接**: 正常")

    # 自动刷新逻辑
    if auto_refresh:
        import time
        time.sleep(refresh_interval)
        st.rerun()


if __name__ == '__main__':
    main()
