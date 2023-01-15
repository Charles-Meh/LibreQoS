use lqos_config::Tunables;
use serde::{Serialize, Deserialize};
use crate::TcHandle;

/// One or more `BusRequest` objects must be included in a `BusSession`
/// request. Each `BusRequest` represents a single request for action
/// or data.
#[derive(Serialize, Deserialize, Clone, Debug, PartialEq)]
pub enum BusRequest {
    /// A generic "is it alive?" test. Returns an `Ack`.
    Ping,

    /// Request total current throughput. Returns a 
    /// `BusResponse::CurrentThroughput` value.
    GetCurrentThroughput,

    /// Retrieve the top N downloads by bandwidth use.
    GetTopNDownloaders(u32),

    /// Retrieves the TopN hosts with the worst RTT, sorted by RTT descending.
    GetWorstRtt(u32),

    /// Retrieves current byte counters for all hosts.
    GetHostCounter,

    /// Requests that the XDP back-end associate an IP address with a
    /// TC (traffic control) handle, and CPU. The "upload" flag indicates
    /// that this is a second channel applied to the SAME network interface,
    /// used for "on-a-stick" mode upload channels.
    MapIpToFlow {
        /// The IP address to map, as a string. It can be IPv4 or IPv6,
        /// and supports CIDR notation for subnets. "192.168.1.1",
        /// "192.168.1.0/24", are both valid.
        ip_address: String,

        /// The TC Handle to which the IP address should be mapped.
        tc_handle: TcHandle,

        /// The CPU on which the TC handle should be shaped.
        cpu: u32,

        /// If true, this is a *second* flow for the same IP range on
        /// the same NIC. Used for handling "on a stick" configurations.
        upload: bool,
    },

    /// Requests that the XDP program unmap an IP address/subnet from
    /// the traffic management system.
    DelIpFlow {
        /// The IP address to unmap. It can be an IPv4, IPv6 or CIDR
        /// subnet.
        ip_address: String,

        /// Should we delete a secondary mapping (for upload)?
        upload: bool,
    },

    /// Clear all XDP IP/TC/CPU mappings.
    ClearIpFlow,

    /// Retreieve list of all current IP/TC/CPU mappings.
    ListIpFlow,

    /// Simulate the previous version's `xdp_pping` command, returning
    /// RTT data for all mapped flows by TC handle.
    XdpPping,

    /// Divide current RTT data into histograms and return the data for
    /// rendering.
    RttHistogram,

    /// Cound the number of mapped and unmapped hosts detected by the
    /// system.
    HostCounts,

    /// Retrieve a list of all unmapped IPs that have been detected
    /// carrying traffic.
    AllUnknownIps,

    /// Reload the `LibreQoS.py` program and return details of the
    /// reload run.
    ReloadLibreQoS,

    /// Retrieve raw queue data for a given circuit ID.
    GetRawQueueData(String), // The string is the circuit ID

    /// Requests a real-time adjustment of the `lqosd` tuning settings
    UpdateLqosDTuning(u64, Tunables),

    /// If running on Equinix (the `equinix_test` feature is enabled),
    /// display a "run bandwidht test" link.
    #[cfg(feature = "equinix_tests")]
    RequestLqosEquinixTest,
}