use chrono::{DateTime, FixedOffset, Utc};
use influxdb2::FromDataPoint;

#[derive(Debug, FromDataPoint)]
pub struct RttRow {
    pub host_id: String,
    pub min: f64,
    pub max: f64,
    pub avg: f64,
    pub time: DateTime<FixedOffset>,
}

impl Default for RttRow {
    fn default() -> Self {
        Self {
            host_id: "".to_string(),
            min: 0.0,
            max: 0.0,
            avg: 0.0,
            time: DateTime::<Utc>::MIN_UTC.into(),
        }
    }
}