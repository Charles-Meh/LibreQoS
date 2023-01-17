use lqos_bus::BusResponse;
use crate::circuit_to_queue::CIRCUIT_TO_QUEUE;

pub fn get_raw_circuit_data(circuit_id: &str) -> BusResponse {
    let reader = CIRCUIT_TO_QUEUE.read();
    if let Some(circuit) = reader.get(circuit_id) {
        if let Ok(json) = serde_json::to_string(circuit) {
            BusResponse::RawQueueData(json)
        } else {
            BusResponse::RawQueueData(String::new())
        }
    } else {
        BusResponse::RawQueueData(String::new())
    }
}
