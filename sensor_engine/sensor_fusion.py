# backend/sensor_engine/sensor_fusion.py
class SensorFusionEngine:
    """센서 데이터 융합 및 상관관계 분석"""
    
    def analyze_sensor_correlations(self, data: Dict) -> Dict:
        """센서 간 상관관계 분석"""
        correlations = {}
        
        # 온도-습도 상관관계
        temp_humidity_corr = np.corrcoef(
            data['temperature'], 
            data['humidity']
        )[0, 1]
        
        # 진동-온도 상관관계
        vibration_temp_corr = np.corrcoef(
            data['vibration'],
            data['temperature']
        )[0, 1]
        
        correlations = {
            'temperature_humidity': float(temp_humidity_corr),
            'vibration_temperature': float(vibration_temp_corr),
            'insights': self._generate_correlation_insights(correlations)
        }
        
        return correlations
    
    def predict_equipment_health(self, sensor_data: Dict) -> Dict:
        """설비 건강도 종합 예측"""
        health_score = 0
        
        # 각 센서 데이터의 가중치 적용
        weights = {
            'temperature': 0.3,
            'humidity': 0.2,
            'vibration': 0.35,
            'noise': 0.15
        }
        
        for metric, weight in weights.items():
            normalized_value = self._normalize_metric(
                sensor_data[metric], 
                THRESHOLDS[metric]
            )
            health_score += (1 - normalized_value) * weight * 100
        
        return {
            'health_score': health_score,
            'status': self._get_health_status(health_score),
            'remaining_useful_life': self._estimate_rul(sensor_data),
            'maintenance_recommendation': self._get_maintenance_advice(health_score)
        }