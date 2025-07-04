from copy import deepcopy

import joblib
import lightgbm as lgb
from alphainspect.dtree import plot_metric_errorbar, plot_importance_box
from loguru import logger
from matplotlib import pyplot as plt

from ml_cs.config import MODEL_FILENAME, INPUT1_PATH, DATE, ASSET, LABEL, DATA_END, FWD_RET, categorical_feature
from ml_cs.config import load_process_regression, load_process_binary  # noqa
from ml_cs.utils import load_dates, walk_forward, get_XyOther

plt.rcParams["font.sans-serif"] = ["SimHei"]  # 设置字体
plt.rcParams["axes.unicode_minus"] = False  # 该语句解决图像中的“-”负号的乱码问题

# 回归
params_regression = {'objective': 'mae', 'metric': {'l1'}, }
# 二分类，平衡
params_binary = {'objective': 'binary', 'metric': {'binary_logloss'}, }

# %%
params = {
    'max_depth': -1,
    'num_leaves': 63,
    'min_data_in_leaf': 50,
    'learning_rate': 0.05,
    'feature_fraction': 0.9,
    'bagging_fraction': 0.9,
    'bagging_freq': 5,
    'lambda_l1': 0.5,
    'lambda_l2': 0.5,
    'verbose': 1,  # -1不显示
    'device_type': 'cpu',
    'seed': 42,
}
params.update(params_binary)
# %%
df = load_process_binary()
logger.info('开始训练...')


# %%
def fit():
    trading_dates = load_dates(INPUT1_PATH, DATE)[:DATA_END]

    models = []
    for i, train_dt, test_dt in walk_forward(trading_dates,
                                             n_splits=1, max_train_size=None, test_size=60, gap=3):
        ds = []
        for start, end in (train_dt, test_dt):
            X, y, other = get_XyOther(df, start, end, DATE, ASSET, LABEL, FWD_RET, label_drop_nulls=True)

            if len(ds) == 0:
                ds.append(lgb.Dataset(X, label=y, categorical_feature=categorical_feature))
            else:
                ds.append(lgb.Dataset(X, label=y, categorical_feature=categorical_feature, reference=ds[0]))

        evals_result = {}  # to record eval results for plotting
        model = lgb.train(
            params,
            train_set=ds[0],
            num_boost_round=500,
            valid_sets=ds,
            valid_names=['train', 'valid'],
            callbacks=[
                lgb.log_evaluation(10),
                lgb.early_stopping(50, first_metric_only=False, verbose=True),
                lgb.record_evaluation(evals_result)
            ],
        )
        # 这里非常重要，否则无法画损失图
        model.evals_result_ = deepcopy(evals_result)
        models.append(model)
    return models


# %% 模型评估
def evaluate(models):
    for metric in params['metric']:
        _, ax = plt.subplots(1, 1, figsize=(10, 5))
        plot_metric_errorbar(models, metric=metric, ax=ax)
    _, ax = plt.subplots(1, 1, figsize=(10, 5))
    plot_importance_box(models, ax=ax)
    plt.show()


# %%
models = fit()
logger.info('保存模型...')
joblib.dump(models, MODEL_FILENAME)

logger.info('加载模型...')
models = joblib.load(MODEL_FILENAME)
evaluate(models)
