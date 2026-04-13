from ortools.sat.python import cp_model

def optimize_portfolio(candidates, budget, risk_constraints=None):
    """
    候補リストの中から、予算内で期待利益(lot_profit)を最大化する組み合わせを
    ナップサック問題としてCP-SATで解く。
    
    二段階最適化:
      第一段階: 呼び出し元でセクター/市場フィルタ＋スコアソート済み
      第二段階: 本関数でリスク制約を適用
        - ボラティリティ上限（プレフィルタ）
        - 集中投資制限（ソルバー制約）
    """
    if risk_constraints is None:
        risk_constraints = {}
    
    max_volatility = risk_constraints.get('max_volatility', None)
    max_concentration = risk_constraints.get('max_concentration', None)
    
    print("-" * 50)
    print(f"【投資最適化】予算: {budget:,} 円 の範囲で期待利益を最大化します...")
    
    # ── 第二段階: ボラティリティ・プレフィルタ ──
    filtered_out = []
    if max_volatility is not None:
        filtered_candidates = []
        for data in candidates:
            if data.get('volatility', 0) > max_volatility:
                filtered_out.append(data)
            else:
                filtered_candidates.append(data)
        if filtered_out:
            print(f"  ⚠ ボラティリティ > {max_volatility} の銘柄を {len(filtered_out)} 社除外:")
            for f in filtered_out:
                print(f"    - {f['name']} ({f['ticker']}): ボラティリティ {f.get('volatility', 0):.3f}")
        candidates = filtered_candidates
    
    if not candidates:
        print("リスク制約を適用した結果、有効な候補がなくなりました。制約を緩めてください。")
        return {
            'success': False,
            'message': 'リスク制約（ボラティリティ上限）を適用した結果、有効な候補がなくなりました。制約を緩めてください。',
            'filtered_out_count': len(filtered_out)
        }
    
    print(f"  ✓ リスク制約通過銘柄数: {len(candidates)} 社")
    
    # ── ソルバー構築 ──
    model = cp_model.CpModel()
    
    # 集中投資制限を考慮した各銘柄の最大株数
    x = {}
    for data in candidates:
        max_shares = int(budget // data['share_price'])
        if max_shares < 0: max_shares = 0
        
        # 集中投資制限: 1銘柄あたりの投資額を予算の max_concentration 以下に制限
        if max_concentration is not None:
            max_cost_per_stock = int(budget * max_concentration)
            max_shares_by_concentration = int(max_cost_per_stock // data['share_price'])
            max_shares = min(max_shares, max_shares_by_concentration)
        
        x[data['ticker']] = model.NewIntVar(0, max_shares, f"x_{data['ticker']}")
    
    # 予算制約
    total_cost_expr = []
    for data in candidates:
        total_cost_expr.append(x[data['ticker']] * data['share_price'])
    model.Add(sum(total_cost_expr) <= budget)
    
    # 目的関数: 期待利益の最大化
    total_profit_expr = []
    for data in candidates:
        total_profit_expr.append(x[data['ticker']] * data['share_profit'])
            
    model.Maximize(sum(total_profit_expr))
    
    solver = cp_model.CpSolver()
    status = solver.Solve(model)
    
    print("-" * 50)
    print("【最適化結果】")
    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        total_invested = 0
        expected_profit = 0
        portfolio = []
        
        for data in candidates:
            shares = solver.Value(x[data['ticker']])
            if shares > 0:
                cost = shares * data['share_price']
                profit = shares * data['share_profit']
                print(f"■ {data['name']} ({data['ticker']}): {shares:,}株購入")
                print(f"   -> 購入金額: {cost:,}円, 単年見込み期待利益: {profit:,}円")
                print(f"      （内訳: 値上がり期待 {data['expected_capital_gain']*shares:,}円 + 配当金期待 {data['expected_dividend']*shares:,}円）")
                total_invested += cost
                expected_profit += profit
                
                portfolio.append({
                    'ticker': data['ticker'],
                    'name': data['name'],
                    'shares': shares,
                    'cost': cost,
                    'profit': profit,
                    'pe': data.get('pe', 0.0),
                    'roe': data.get('roe', 0.0),
                    'custom_return': data.get('custom_return', 0.0),
                    'expected_capital_gain': data['expected_capital_gain']*shares,
                    'expected_dividend': data['expected_dividend']*shares,
                    'analyst_rating': data.get('analyst_rating', '-')
                })
                
        print(f"\n合計購入金額: {total_invested:,} 円 （残高: {budget - total_invested:,} 円）")
        print(f"見込み期待利益合計: {expected_profit:,} 円")
        
        return {
            'success': True,
            'portfolio': portfolio,
            'total_invested': total_invested,
            'expected_profit': expected_profit,
            'remaining_budget': budget - total_invested,
            'filtered_out_count': len(filtered_out)
        }
    else:
        print("予算内で有効な最適解が見つかりませんでした（株価が高すぎて一単元も買えない等）。")
        return {
            'success': False,
            'message': '予算内で有効な最適解が見つかりませんでした（株価が高すぎて一単元も買えない等）。',
            'filtered_out_count': len(filtered_out)
        }
