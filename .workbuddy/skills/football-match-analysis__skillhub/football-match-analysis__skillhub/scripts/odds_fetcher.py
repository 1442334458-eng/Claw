"""
The Odds API 赔率获取器
获取实时博彩赔率数据，支持世界杯等赛事
"""

import os
import json
from typing import Dict, List, Optional

# 使用 coze_workload_identity 发起请求
from coze_workload_identity import requests


class OddsFetcher:
    """赔率数据获取器"""
    
    BASE_URL = "https://api.the-odds-api.com/v4"
    
    def __init__(self, skill_id: int = None):
        # 从环境变量读取API Key（通过skill_draft_credential配置后自动注入）
        if skill_id:
            self.api_key = os.getenv(f"COZE_THE_ODDS_API_{skill_id}")
        else:
            self.api_key = os.getenv("COZE_THE_ODDS_API_7645824779949260815")
        
        if not self.api_key:
            raise ValueError("缺少The Odds API凭证，请先配置API Key")
    
    def get_world_cup_odds(self, markets: str = "h2h", 
                           regions: str = "eu,us") -> List[Dict]:
        """获取世界杯所有比赛赔率"""
        url = f"{self.BASE_URL}/sports/soccer_fifa_world_cup/odds/"
        params = {
            "apiKey": self.api_key,
            "regions": regions,
            "markets": markets,
            "oddsFormat": "decimal"
        }
        
        response = requests.get(url, params=params, timeout=30)
        if response.status_code != 200:
            raise Exception(f"API请求失败: {response.status_code}, {response.text}")
        
        return response.json()
    
    def get_match_odds(self, home_team: str, away_team: str,
                       sport: str = "soccer_fifa_world_cup") -> Optional[Dict]:
        """获取指定比赛的赔率"""
        all_odds = self.get_world_cup_odds() if sport == "soccer_fifa_world_cup" else []
        
        for match in all_odds:
            if (home_team.lower() in match.get('home_team', '').lower() and
                away_team.lower() in match.get('away_team', '').lower()):
                return match
        
        return None
    
    def get_average_odds(self, match_data: Dict) -> Dict:
        """计算多平台平均赔率(去vig)"""
        probs_home = []
        probs_draw = []
        probs_away = []
        home_team = match_data['home_team']
        away_team = match_data['away_team']
        
        for bookmaker in match_data.get('bookmakers', []):
            for market in bookmaker.get('markets', []):
                outcomes = {o['name']: o['price'] for o in market.get('outcomes', [])}
                
                home_key = home_team
                away_key = away_team
                draw_key = 'Draw'
                
                if home_key in outcomes and away_key in outcomes and draw_key in outcomes:
                    probs_home.append(1 / outcomes[home_key])
                    probs_draw.append(1 / outcomes[draw_key])
                    probs_away.append(1 / outcomes[away_key])
        
        if not probs_home:
            return None
        
        total_raw = sum(probs_home)/len(probs_home) + sum(probs_draw)/len(probs_draw) + sum(probs_away)/len(probs_away)
        
        return {
            'home_team': home_team,
            'away_team': away_team,
            'prob_home': round(sum(probs_home)/len(probs_home) / total_raw * 100, 1),
            'prob_draw': round(sum(probs_draw)/len(probs_draw) / total_raw * 100, 1),
            'prob_away': round(sum(probs_away)/len(probs_away) / total_raw * 100, 1),
            'vig': round((total_raw - 1) * 100, 1),
            'num_bookmakers': len(probs_home)
        }
    
    def value_scan(self, model_predictions: List[Dict], 
                   threshold: float = 3.0) -> List[Dict]:
        """批量扫描价值信号"""
        all_odds = self.get_world_cup_odds()
        value_matches = []
        
        for match in all_odds:
            avg = self.get_average_odds(match)
            if not avg:
                continue
            
            for pred in model_predictions:
                if (pred['team_a'].lower() in avg['home_team'].lower() or
                    pred['team_b'].lower() in avg['home_team'].lower()):
                    
                    market_prob = {
                        'win_a': avg['prob_home'],
                        'draw': avg['prob_draw'],
                        'win_b': avg['prob_away']
                    }
                    
                    from prediction_engine import FootballPredictionEngine
                    engine = FootballPredictionEngine()
                    edges = engine.value_detection(pred['final'], market_prob, threshold)
                    
                    has_value = any(v['is_value'] for v in edges.values())
                    if has_value:
                        value_matches.append({
                            'match': f"{avg['home_team']} vs {avg['away_team']}",
                            'market': market_prob,
                            'model': pred['final'],
                            'edges': edges
                        })
        
        return value_matches


if __name__ == "__main__":
    fetcher = OddsFetcher()
    odds = fetcher.get_world_cup_odds()
    print(f"获取到 {len(odds)} 场世界杯比赛赔率")
    
    for match in odds[:3]:
        avg = fetcher.get_average_odds(match)
        if avg:
            print(f"{avg['home_team']} vs {avg['away_team']}: "
                  f"{avg['prob_home']}%/{avg['prob_draw']}%/{avg['prob_away']}% "
                  f"(vig: {avg['vig']}%, {avg['num_bookmakers']}家)")
