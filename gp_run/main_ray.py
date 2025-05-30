"""
1. 准备数据
    date,asset,features,..., returns,...,labels

features建议提前做好预处理。因为在GP中计算效率低下，特别是行业中性化等操作强烈建议在提前做。因为
1. `ts_`。按5000次股票，要计算5000次
2. `cs_`。按1年250天算，要计算250次
3. `gp_`计算次数是`cs_`计算的n倍。按30个行业，1年250天，要计算30*250=7500次

ROCP=ts_return，不移动位置，用来做特征。前移shift(-x)就只能做标签了

returns是shift前移的简单收益率，用于事后求分组收益
1. 对数收益率方便进行时序上的累加
2. 简单收益率方便横截面上进行等权
log_return = ln(1+simple_return)

labels是因变量
1. 可能等于returns
2. 可能是超额收益率
3. 可能是0/1等分类标签

样本内外的思考
一开始，为了计算样本内外，我参考了机器学习的方法，提前将数据分成了训练集和测试集，然后分别计算因子值和IC/IR，
运行了一段时间后忽然发现，对于个体来说表达式已经明确了，每日的IC已经是确定了，而训练集与测试集的IC区别只是mean(IC)时间段的差异。
所以整体一起计算，然后分段计算IC/IR速度能快上不少。

"""
import os
import sys
from pathlib import Path

# 修改当前目录到上层目录，方便跨不同IDE中使用
pwd = str(Path(__file__).parents[1])
os.chdir(pwd)
sys.path.append(pwd)
print("pwd:", os.getcwd())
# ====================
import operator
import pickle
import socket
from datetime import datetime
from itertools import count
from pathlib import Path

import polars as pl
import ray
from deap import base, creator
from loguru import logger
import more_itertools
from ray.util import ActorPool
# ==========================
# !!! 非常重要。给deap打补丁
from gp_base_cs.deap_patch import *  # noqa
from gp_base_cs.base import print_population, population_to_exprs, filter_exprs
# ==========================
# TODO 单资产多因子，计算时序IC,使用gp_base_ts
# TODO 多资产多因子，计算截面IC,使用gp_base_cs
from gp_base_cs.custom import add_constants, add_operators, add_factors, RET_TYPE
from gp_base_cs.helper import batched_exprs, fill_fitness

# ==========================

logger.remove()  # 这行很关键，先删除logger自动产生的handler，不然会出现重复输出的问题
logger.add(sys.stderr, level='INFO')  # 只输出INFO以上的日志
# ======================================
# TODO 必须元组，1表示找最大值,-1表示找最小值
FITNESS_WEIGHTS = (1.0, 1.0)

# TODO y表示类别标签、因变量、输出变量，需要与数据文件字段对应
LABEL_y = 'RETURN_OO_1'

# TODO: 数据准备，脚本将取df_input，可运行`data`下脚本生成
dt1 = datetime(2021, 1, 1)
# ======================================
# 日志路径
LOG_DIR = Path('log')
LOG_DIR.mkdir(parents=True, exist_ok=True)

# TODO 初始化时指定要共享的模块，这里用的多资产多因子挖掘
ray.init(runtime_env={"py_modules": ['gp_base_cs', 'gp_base_ts']})


@ray.remote(num_cpus=1)
class BatchExprActor:
    # 每台机器只运行一个任务，因为polars是多线程
    df = None
    ip_path = {
        # TODO 需要提前将数据复制到不同机器对应的目录，数据需要完全一样
        # 如果对应机器不启用一定要注释
        # '192.168.28.218': r'D:\alpha_examples-main\data\data.parquet',
        '127.0.0.1': r'D:\GitHub\alpha_examples\data\data.parquet',
    }

    def get_nodes_count(self):
        return len(self.ip_path)

    def get_path_by_ip(self, ips):
        """IP转数据地址"""
        # 添加本地IP,方便单机跑多个actor
        ips = ['127.0.0.1'] + ips
        for ip in reversed(ips):
            path = self.ip_path.get(ip, None)
            if path is not None:
                return path
        return None

    def load_data(self):
        """加载数据"""
        if self.df is not None:
            return self.df

        hostname = socket.gethostname()
        ips = socket.gethostbyname_ex(hostname)
        print('每个进程只加载一次数据', ips)
        path = self.get_path_by_ip(ips[2])
        self.df = pl.read_parquet(path)
        return self.df

    def process(self, batch_id, exprs_list, gen, label, split_date):
        """批量计算"""
        return batched_exprs(batch_id, exprs_list, gen, label, split_date, self.load_data())


# TODO 种群如果非常大，但内存比较小，可以分批计算，每次计算BATCH_SIZE个个体
BATCH_SIZE = 50
DIVIDE_SIZE = BatchExprActor.get_nodes_count()  # TODO 每个节点启动1个actor，CPU可能占不满
DIVIDE_SIZE = 2  # TODO 单机启动2个actor，可能会cpu占满
# 根据节点数生成对应数量的actor
pool = ActorPool([BatchExprActor.remote() for i in range(DIVIDE_SIZE)])


def map_exprs(evaluate, invalid_ind, gen, label, split_date):
    """原本是一个普通的map或多进程map，个体都是独立计算
    但这里考虑到表达式很相似，可以重复利用公共子表达式，
    所以决定种群一起进行计算，返回结果评估即可
    """
    g = next(gen)
    # 保存原始表达式，立即保存是防止崩溃后丢失信息, 注意：这里没有存fitness
    with open(LOG_DIR / f'exprs_{g:04d}.pkl', 'wb') as f:
        pickle.dump(invalid_ind, f)

    # 读取历史fitness
    try:
        with open(LOG_DIR / f'fitness_cache.pkl', 'rb') as f:
            fitness_results = pickle.load(f)
    except FileNotFoundError:
        fitness_results = {}

    logger.info("表达式转码...")
    # DEAP表达式转sympy表达式。约定以GP_开头，表示遗传编程
    exprs_list = population_to_exprs(invalid_ind, globals().copy())
    exprs_old = exprs_list.copy()
    exprs_list = filter_exprs(exprs_list, pset, RET_TYPE, fitness_results)

    if len(exprs_list) > 0:
        # 并行计算，木桶效益，最好多台机器能差不多时间算完
        new_results = pool.map(lambda a, v: a.process.remote(*v, g, label, split_date), enumerate(more_itertools.batched(exprs_list, BATCH_SIZE)))
        # new_results = pool.map(lambda a, v: a.process.remote(*v, g, label, split_date), enumerate(more_itertools.divide(DIVIDE_SIZE, exprs_list)))

        for r in new_results:
            # 合并历史与最新的fitness
            fitness_results.update(r)

        # 保存适应度，方便下一代使用
        with open(LOG_DIR / f'fitness_cache.pkl', 'wb') as f:
            pickle.dump(fitness_results, f)
    else:
        pass

    # 取评估函数值，多目标。
    return fill_fitness(exprs_old, fitness_results)


# ======================================
# 这里的ret_type只要与addPrimitive对应即可
pset = gp.PrimitiveSetTyped("MAIN", [], RET_TYPE)
pset = add_constants(pset)
pset = add_operators(pset)
pset = add_factors(pset)

# 可支持多目标优化
creator.create("FitnessMulti", base.Fitness, weights=FITNESS_WEIGHTS)
creator.create("Individual", gp.PrimitiveTree, fitness=creator.FitnessMulti)

toolbox = base.Toolbox()
toolbox.register("expr", gp.genHalfAndHalf, pset=pset, min_=2, max_=5)
toolbox.register("individual", tools.initIterate, creator.Individual, toolbox.expr)
toolbox.register("population", tools.initRepeat, list, toolbox.individual)
toolbox.register("select", tools.selTournament, tournsize=3)  # 目标优化
# toolbox.register("select", tools.selNSGA2)  # 多目标优化 FITNESS_WEIGHTS = (1.0, 1.0)
toolbox.register("mate", gp.cxOnePoint)
toolbox.register("expr_mut", gp.genFull, min_=0, max_=2)
toolbox.register("mutate", gp.mutUniform, expr=toolbox.expr_mut, pset=pset)
toolbox.decorate("mate", gp.staticLimit(key=operator.attrgetter("height"), max_value=17))
toolbox.decorate("mutate", gp.staticLimit(key=operator.attrgetter("height"), max_value=17))
toolbox.register("evaluate", print)  # 不单独做评估了，在map中一并做了
toolbox.register('map', map_exprs, gen=count(), label=LABEL_y, split_date=dt1)

# 只统计一个指标更清晰
stats = tools.Statistics(lambda ind: ind.fitness.values)
# 打补丁后，名人堂可以用nan了，如果全nan会报警
stats.register("avg", np.nanmean, axis=0)
stats.register("std", np.nanstd, axis=0)
stats.register("min", np.nanmin, axis=0)
stats.register("max", np.nanmax, axis=0)


def main():
    # TODO: 伪随机种子，同种子可复现
    random.seed(9527)

    # TODO: 初始种群大小
    pop = toolbox.population(n=1000)
    # TODO: 名人堂，表示最终选优多少个体
    hof = tools.HallOfFame(1000)

    # 使用修改版的eaMuPlusLambda
    population, logbook = eaMuPlusLambda(pop, toolbox,
                                         # 选多少个做为下一代，每次生成多少新个体
                                         mu=150, lambda_=100,
                                         # 交叉率、变异率，代数
                                         cxpb=0.5, mutpb=0.1, ngen=2,
                                         # 名人堂参数
                                         # alpha=0.05, beta=10, gamma=0.25, rho=0.9,
                                         stats=stats, halloffame=hof, verbose=True,
                                         # 早停
                                         early_stopping_rounds=5)

    return population, logbook, hof


if __name__ == "__main__":
    print('另行执行`tensorboard --logdir=runs`，然后在浏览器中访问`http://localhost:6006/`，可跟踪运行情况')
    logger.warning('运行前请检查`fitness_cache.pkl`是否要手工删除。数据集、切分时间发生了变化一定要删除，否则重复的表达式不会参与计算')

    population, logbook, hof = main()

    # 保存名人堂
    with open(LOG_DIR / f'hall_of_fame.pkl', 'wb') as f:
        pickle.dump(hof, f)

    print('=' * 60)
    print(logbook)

    print('=' * 60)
    print_population(hof, globals().copy())
