from ortools.sat.python import cp_model

def optimize_portfolio(candidates, budget, risk_constraints=None):
    """
    候補リスト(candidates)の中から、予算内(budget)で独自スコア(custom_score_per_share)を最大化する組み合わせを
    ナップサック問題としてCP-SATで解く。
    """
    max_concentration = risk_constraints['max_concentration']
    
    if not candidates:
        return {
            'success': False,
            'message': '有効な候補がありません。制約を緩めてください。'
        }
    
    # ── ソルバー構築 ──
    model = cp_model.CpModel()
    
    # 集中投資制限を考慮した各銘柄の最大株数=変数の宣言時に最小値と最大値を設定する必要がある。
    x = {}
    for data in candidates:
        max_shares = int(budget // data['share_price'])
        if max_shares < 0:
            max_shares = 0
        
        # 集中投資制限: 1銘柄あたりの投資額を予算の max_concentration 以下に制限
        max_cost_per_stock = int(budget * max_concentration)
        max_shares_by_concentration = int(max_cost_per_stock // data['share_price'])
        max_shares = min(max_shares, max_shares_by_concentration)
        
        x[data['ticker']] = model.NewIntVar(lb=0, ub=max_shares, name=f"x_{data['ticker']}")    # 変数x(購入する銘柄の数)
    
    # ── 予算制約 ──
    total_cost_expr = []
    for data in candidates:
        total_cost_expr.append(x[data['ticker']] * data['share_price'])
    model.Add(sum(total_cost_expr) <= budget) 
    
    # 目的関数: 独自スコア（custom_score_per_share）の最大化
    total_score_expr = []
    for data in candidates:
        total_score_expr.append(x[data['ticker']] * data['custom_score_per_share'])
            
    model.Maximize(sum(total_score_expr))
    
    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    
    # ── 最適化結果の出力 ──
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        total_invested = 0
        expected_profit = 0
        portfolio = []
        
        for data in candidates:
            shares = solver.Value(x[data['ticker']])
            if shares > 0:
                cost = shares * data['share_price']     # 購入金額
                profit = shares * data['share_profit']  # 利益額
                total_invested += cost                  # 合計購入金額  
                expected_profit += profit               # 合計利益額
                
                portfolio.append({
                    'ticker': data['ticker'],
                    'name': data['name'],
                    'share_price': data['share_price'],
                    'shares': shares,
                    'cost': cost,
                    'profit': profit,
                    'pe': data.get('pe', 0.0),
                    'roe': data.get('roe', 0.0),
                    'custom_score_rate': data.get('custom_score_rate', 0.0),
                    'expected_capital_gain': data['expected_capital_gain']*shares,
                    'expected_dividend': data['expected_dividend']*shares,
                    'analyst_rating': data.get('analyst_rating', '-')
                })
        
        return {
            'success': True,
            'portfolio': portfolio,
            'total_invested': total_invested,
            'expected_profit': expected_profit,
            'remaining_budget': budget - total_invested
        }
    else:
        return {
            'success': False,
            'message': '予算内で有効な最適解が見つかりませんでした（株価が高すぎて一単元も買えない等）。'
        }
