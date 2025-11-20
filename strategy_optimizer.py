#!/usr/bin/env python3
"""
策略参数优化器

使用多种优化算法自动寻找最优参数组合：
- 网格搜索（Grid Search）
- 随机搜索（Random Search）
- 贝叶斯优化（Bayesian Optimization）
- 遗传算法（Genetic Algorithm）
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Callable
from scipy.optimize import differential_evolution, minimize
from sklearn.model_selection import ParameterGrid
import logging
from tqdm import tqdm
import json
from datetime import datetime

from advanced_backtest import BacktestConfig, AdvancedBacktester, backtest_from_ml_data

logger = logging.getLogger(__name__)


class StrategyOptimizer:
    """策略参数优化器"""

    def __init__(self, data_path: str, model_path: str):
        """
        初始化优化器

        Args:
            data_path: 数据文件路径
            model_path: 模型文件路径
        """
        self.data_path = data_path
        self.model_path = model_path
        self.results = []

    def objective_function(self, params: List[float], metric='sharpe_ratio') -> float:
        """
        目标函数

        Args:
            params: 参数列表 [stop_loss, take_profit, position_size, leverage]
            metric: 优化目标指标

        Returns:
            负的指标值（因为优化算法是最小化）
        """
        stop_loss, take_profit, position_size, leverage = params

        # 创建配置
        config = BacktestConfig(
            initial_capital=10000,
            position_size=position_size,
            leverage=leverage,
            stop_loss_pct=stop_loss,
            take_profit_pct=take_profit
        )

        try:
            # 运行回测
            backtester, result = backtest_from_ml_data(
                self.data_path,
                self.model_path,
                config
            )

            # 获取指标
            metric_value = getattr(result, metric, 0)

            # 记录结果
            self.results.append({
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'position_size': position_size,
                'leverage': leverage,
                metric: metric_value,
                'total_return': result.total_return,
                'max_drawdown': result.max_drawdown,
                'win_rate': result.win_rate
            })

            # 返回负值（最小化）
            return -metric_value

        except Exception as e:
            logger.error(f"回测失败: {e}")
            return 1e10  # 返回一个很大的值表示失败

    def grid_search(self, param_grid: Dict, metric='sharpe_ratio') -> Dict:
        """
        网格搜索

        Args:
            param_grid: 参数网格
                {
                    'stop_loss': [0.01, 0.015, 0.02],
                    'take_profit': [0.02, 0.03, 0.04],
                    'position_size': [100, 200],
                    'leverage': [5, 10, 15]
                }
            metric: 优化目标

        Returns:
            最优参数
        """
        logger.info("开始网格搜索...")

        param_combinations = list(ParameterGrid(param_grid))
        logger.info(f"总共{len(param_combinations)}个参数组合")

        best_score = float('-inf')
        best_params = None

        for params in tqdm(param_combinations, desc="网格搜索"):
            score = -self.objective_function(
                [params['stop_loss'], params['take_profit'],
                 params['position_size'], params['leverage']],
                metric
            )

            if score > best_score:
                best_score = score
                best_params = params

        logger.info(f"最优{metric}: {best_score:.4f}")
        logger.info(f"最优参数: {best_params}")

        return best_params

    def random_search(self, param_ranges: Dict, n_iter=100, metric='sharpe_ratio') -> Dict:
        """
        随机搜索

        Args:
            param_ranges: 参数范围
                {
                    'stop_loss': (0.01, 0.05),
                    'take_profit': (0.02, 0.08),
                    'position_size': (50, 500),
                    'leverage': (5, 20)
                }
            n_iter: 迭代次数
            metric: 优化目标

        Returns:
            最优参数
        """
        logger.info(f"开始随机搜索（{n_iter}次迭代）...")

        best_score = float('-inf')
        best_params = None

        for i in tqdm(range(n_iter), desc="随机搜索"):
            # 随机采样参数
            params = {
                'stop_loss': np.random.uniform(*param_ranges['stop_loss']),
                'take_profit': np.random.uniform(*param_ranges['take_profit']),
                'position_size': np.random.uniform(*param_ranges['position_size']),
                'leverage': np.random.uniform(*param_ranges['leverage'])
            }

            score = -self.objective_function(
                [params['stop_loss'], params['take_profit'],
                 params['position_size'], params['leverage']],
                metric
            )

            if score > best_score:
                best_score = score
                best_params = params

        logger.info(f"最优{metric}: {best_score:.4f}")
        logger.info(f"最优参数: {best_params}")

        return best_params

    def bayesian_optimization(self, param_ranges: Dict, n_iter=50, metric='sharpe_ratio') -> Dict:
        """
        贝叶斯优化（使用差分进化算法近似）

        Args:
            param_ranges: 参数范围
            n_iter: 迭代次数
            metric: 优化目标

        Returns:
            最优参数
        """
        logger.info(f"开始贝叶斯优化（{n_iter}次迭代）...")

        # 定义边界
        bounds = [
            param_ranges['stop_loss'],
            param_ranges['take_profit'],
            param_ranges['position_size'],
            param_ranges['leverage']
        ]

        # 运行优化
        result = differential_evolution(
            lambda x: self.objective_function(x, metric),
            bounds,
            maxiter=n_iter,
            workers=1,
            updating='immediate',
            disp=True
        )

        best_params = {
            'stop_loss': result.x[0],
            'take_profit': result.x[1],
            'position_size': result.x[2],
            'leverage': result.x[3]
        }

        logger.info(f"最优{metric}: {-result.fun:.4f}")
        logger.info(f"最优参数: {best_params}")

        return best_params

    def genetic_algorithm(self, param_ranges: Dict, population_size=20,
                         generations=10, metric='sharpe_ratio') -> Dict:
        """
        遗传算法

        Args:
            param_ranges: 参数范围
            population_size: 种群大小
            generations: 代数
            metric: 优化目标

        Returns:
            最优参数
        """
        logger.info(f"开始遗传算法优化（种群{population_size}, {generations}代）...")

        # 初始化种群
        population = []
        for _ in range(population_size):
            individual = [
                np.random.uniform(*param_ranges['stop_loss']),
                np.random.uniform(*param_ranges['take_profit']),
                np.random.uniform(*param_ranges['position_size']),
                np.random.uniform(*param_ranges['leverage'])
            ]
            population.append(individual)

        best_individual = None
        best_fitness = float('-inf')

        for generation in range(generations):
            logger.info(f"第{generation + 1}代...")

            # 评估适应度
            fitness_scores = []
            for individual in tqdm(population, desc=f"第{generation+1}代"):
                fitness = -self.objective_function(individual, metric)
                fitness_scores.append(fitness)

                if fitness > best_fitness:
                    best_fitness = fitness
                    best_individual = individual.copy()

            # 选择（锦标赛选择）
            new_population = []
            for _ in range(population_size):
                # 随机选择两个个体
                idx1, idx2 = np.random.choice(population_size, 2, replace=False)
                # 选择适应度更好的
                if fitness_scores[idx1] > fitness_scores[idx2]:
                    parent = population[idx1]
                else:
                    parent = population[idx2]
                new_population.append(parent.copy())

            # 交叉和变异
            for i in range(0, population_size - 1, 2):
                # 交叉
                if np.random.rand() < 0.7:  # 交叉概率
                    crossover_point = np.random.randint(1, 4)
                    new_population[i][:crossover_point], new_population[i+1][:crossover_point] = \
                        new_population[i+1][:crossover_point], new_population[i][:crossover_point]

                # 变异
                for j in range(4):
                    if np.random.rand() < 0.1:  # 变异概率
                        param_name = ['stop_loss', 'take_profit', 'position_size', 'leverage'][j]
                        new_population[i][j] = np.random.uniform(*param_ranges[param_name])

            population = new_population

        best_params = {
            'stop_loss': best_individual[0],
            'take_profit': best_individual[1],
            'position_size': best_individual[2],
            'leverage': best_individual[3]
        }

        logger.info(f"最优{metric}: {best_fitness:.4f}")
        logger.info(f"最优参数: {best_params}")

        return best_params

    def export_results(self, filename='optimization_results.json'):
        """导出优化结果"""
        if not self.results:
            logger.warning("没有结果可导出")
            return

        # 转换为DataFrame
        df = pd.DataFrame(self.results)

        # 导出JSON
        results_dict = {
            'timestamp': datetime.now().isoformat(),
            'total_tests': len(self.results),
            'best_result': df.nlargest(1, 'sharpe_ratio').to_dict('records')[0],
            'all_results': self.results
        }

        with open(filename, 'w') as f:
            json.dump(results_dict, f, indent=2)

        logger.info(f"结果已导出到: {filename}")

        # 导出CSV
        csv_filename = filename.replace('.json', '.csv')
        df.to_csv(csv_filename, index=False)
        logger.info(f"结果已导出到: {csv_filename}")


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='策略参数优化器')
    parser.add_argument('--data', required=True, help='数据文件路径')
    parser.add_argument('--model', required=True, help='模型文件路径')
    parser.add_argument('--method', default='bayesian',
                       choices=['grid', 'random', 'bayesian', 'genetic'],
                       help='优化方法')
    parser.add_argument('--metric', default='sharpe_ratio',
                       choices=['sharpe_ratio', 'total_return', 'profit_factor'],
                       help='优化目标')
    parser.add_argument('--iterations', type=int, default=50, help='迭代次数')

    args = parser.parse_args()

    # 配置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 创建优化器
    optimizer = StrategyOptimizer(args.data, args.model)

    # 参数范围
    param_ranges = {
        'stop_loss': (0.01, 0.05),
        'take_profit': (0.02, 0.08),
        'position_size': (50.0, 500.0),
        'leverage': (5.0, 20.0)
    }

    # 运行优化
    if args.method == 'grid':
        param_grid = {
            'stop_loss': [0.01, 0.015, 0.02, 0.025, 0.03],
            'take_profit': [0.02, 0.03, 0.04, 0.05],
            'position_size': [100, 200, 300],
            'leverage': [5, 10, 15]
        }
        best_params = optimizer.grid_search(param_grid, args.metric)

    elif args.method == 'random':
        best_params = optimizer.random_search(param_ranges, args.iterations, args.metric)

    elif args.method == 'bayesian':
        best_params = optimizer.bayesian_optimization(param_ranges, args.iterations, args.metric)

    elif args.method == 'genetic':
        best_params = optimizer.genetic_algorithm(param_ranges, 20, args.iterations // 10, args.metric)

    # 导出结果
    optimizer.export_results()

    print("\n" + "="*60)
    print("优化完成！")
    print("="*60)
    print(f"最优参数:")
    for key, value in best_params.items():
        print(f"  {key}: {value:.4f}")


if __name__ == '__main__':
    main()
