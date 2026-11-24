"""Original model factories with explicit task seeds and crossed fit budgets."""
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.ensemble import RandomForestClassifier, ExtraTreesClassifier, HistGradientBoostingClassifier
from sklearn.ensemble import RandomForestRegressor, ExtraTreesRegressor, HistGradientBoostingRegressor

def model(algo,task):
    SEED = 20261023
    if algo=='LR':return LogisticRegression(C=.1,max_iter=2500,solver='lbfgs',random_state=SEED)
    if algo=='RF':return RandomForestClassifier(n_estimators=80,max_depth=6,min_samples_leaf=20,max_features='sqrt',n_jobs=1,random_state=SEED)
    if algo=='ET':return ExtraTreesClassifier(n_estimators=80,max_depth=6,min_samples_leaf=20,max_features='sqrt',n_jobs=1,random_state=SEED)
    if algo=='HGB':return HistGradientBoostingClassifier(max_iter=80,max_leaf_nodes=15,max_depth=5,min_samples_leaf=30,l2_regularization=1,learning_rate=.05,early_stopping=False,random_state=SEED)
    if algo=='XGB':
        from xgboost import XGBClassifier
        return XGBClassifier(n_estimators=100,max_depth=3,min_child_weight=10,reg_lambda=5,learning_rate=.05,subsample=.8,colsample_bytree=.8,tree_method='hist',n_jobs=1,random_state=SEED,eval_metric='logloss' if task=='BINARY' else 'mlogloss')
    if algo=='LGBM':
        from lightgbm import LGBMClassifier
        return LGBMClassifier(n_estimators=100,num_leaves=15,max_depth=5,min_child_samples=30,reg_lambda=5,learning_rate=.05,n_jobs=1,random_state=SEED,verbosity=-1,deterministic=True,force_col_wise=True)
    raise ValueError(algo)

def classifier(algo,task):
    m=model(algo,task)
    # Fixed computational budget, declared before any crossed-search score.
    if algo in ['RF','ET']:m.set_params(n_estimators=48)
    elif algo=='HGB':m.set_params(max_iter=60)
    elif algo in ['XGB','LGBM']:m.set_params(n_estimators=64)
    return m

def regressor(algo):
    SEED = 20261024
    if algo=='RIDGE':return Ridge(alpha=10.,solver='cholesky')
    if algo in ['RF','ET']:
        cls=RandomForestRegressor if algo=='RF' else ExtraTreesRegressor
        return cls(n_estimators=48,max_depth=6,min_samples_leaf=20,max_features='sqrt',n_jobs=1,random_state=SEED)
    if algo=='HGB':return HistGradientBoostingRegressor(loss='squared_error',max_iter=60,max_leaf_nodes=15,max_depth=5,min_samples_leaf=30,l2_regularization=1,learning_rate=.05,early_stopping=False,random_state=SEED)
    if algo=='XGB':
        from xgboost import XGBRegressor
        return XGBRegressor(objective='reg:squarederror',n_estimators=64,max_depth=3,min_child_weight=10,reg_lambda=5,learning_rate=.05,subsample=.8,colsample_bytree=.8,tree_method='hist',n_jobs=1,random_state=SEED)
    if algo=='LGBM':
        from lightgbm import LGBMRegressor
        return LGBMRegressor(objective='regression',n_estimators=64,num_leaves=15,max_depth=5,min_child_samples=30,reg_lambda=5,learning_rate=.05,n_jobs=1,random_state=SEED,verbosity=-1,deterministic=True,force_col_wise=True)
    raise ValueError(algo)
