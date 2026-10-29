#include <core.p4>
#include <v1model.p4>

// All modes share one pipeline. Only S1's host-facing port selects paths.
header ethernet_t { bit<48> dst; bit<48> src; bit<16> kind; }
header ipv4_t {
    bit<4> version; bit<4> ihl; bit<8> tos; bit<16> len;
    bit<16> id; bit<3> flags; bit<13> offset; bit<8> ttl;
    bit<8> protocol; bit<16> checksum; bit<32> src; bit<32> dst;
}
header udp_t { bit<16> src; bit<16> dst; bit<16> len; bit<16> checksum; }
// EtherType 0x88b5: addressed counter requests and replies toward the source.
header query_t { bit<8> op; bit<8> port; bit<8> switch_id; bit<8> nonce; bit<64> bytes; }
struct headers { ethernet_t eth; ipv4_t ip; udp_t udp; query_t query; }
struct metadata { bit<1> data; }
parser Parse(packet_in p, out headers h, inout metadata m,
             inout standard_metadata_t sm) {
    state start {
        m.data = 0;
        p.extract(h.eth);
        transition select(h.eth.kind) { 0x0800: ip; 0x88b5: query; default: accept; }
    }
    state ip {
        p.extract(h.ip);
        transition select(h.ip.version, h.ip.ihl, h.ip.offset, h.ip.flags, h.ip.protocol) {
            (4, 5, 0, 0, 17): udp;
            (4, 5, 0, 2, 17): udp;
            default: accept;
        }
    }
    state udp { p.extract(h.udp); m.data = 1; transition accept; }
    state query { p.extract(h.query); transition accept; }
}
control Verify(inout headers h, inout metadata m) { apply { } }
register<bit<64>>(512) port_bytes;
control MyIngress(inout headers h, inout metadata m, inout standard_metadata_t sm) {

    register<bit<48>>(65536) last_seen;
    register<bit<32>>(65536) flow_tag;
    register<bit<1>>(65536) flow_valid;
    register<bit<1>>(65536) flow_path;
    register<bit<32>>(1) flowlet_changes;
    action drop() { mark_to_drop(sm); }
    action forward(bit<9> port) { sm.egress_spec = port; }
    action balance(bit<8> mode, bit<48> gap_us) {
        bit<32> fingerprint;
        bit<32> slot;
        bit<1> path;
        bit<1> valid;
        bit<32> tag;
        bit<48> previous;
        bit<32> changes;
        hash(fingerprint, HashAlgorithm.crc32, (bit<32>)0,
             {h.ip.src, h.ip.dst, h.ip.protocol, h.udp.src, h.udp.dst}, (bit<32>)0xffffffff);
        slot = fingerprint & 65535;
        path = (bit<1>)(fingerprint >> 16);
        if (mode == 1) { random(path, (bit<1>)0, (bit<1>)1); }
        if (mode == 2) {
            // A fingerprint protects unrelated flows sharing a register slot.
            @atomic {
                last_seen.read(previous, slot);
                flow_tag.read(tag, slot);
                flow_valid.read(valid, slot);
                flow_path.read(path, slot);
                if (valid == 0 || tag != fingerprint) {
                    random(path, (bit<1>)0, (bit<1>)1);
                } else if (sm.ingress_global_timestamp - previous > gap_us) {
                    bit<1> new_path;
                    random(new_path, (bit<1>)0, (bit<1>)1);
                    if (new_path != path) {
                        flowlet_changes.read(changes, 0);
                        flowlet_changes.write(0, changes + 1);
                    }
                    path = new_path;
                }
                last_seen.write(slot, sm.ingress_global_timestamp);
                flow_tag.write(slot, fingerprint);
                flow_valid.write(slot, 1);
                flow_path.write(slot, path);
            }
        }
        sm.egress_spec = (bit<9>)path + 2;
    }
    action answer_query() {
        bit<48> old_src;
        port_bytes.read(h.query.bytes, (bit<32>)h.query.port);
        h.query.op = 1;
        old_src = h.eth.src; h.eth.src = h.eth.dst; h.eth.dst = old_src;
        sm.egress_spec = sm.ingress_port;
    }
    table query_route {
        key = { h.query.switch_id: exact; }
        actions = { answer_query; forward; drop; }
        size = 4;
        default_action = drop();
    }
    table query_return {
        actions = { forward; }
        default_action = forward(1);
    }
    table first_hop {
        key = { sm.ingress_port: exact; }
        actions = { balance; NoAction; }
        size = 4;
        default_action = NoAction();
    }
    table destination {
        key = { h.ip.dst: lpm; }
        actions = { forward; drop; }
        size = 16;
        default_action = drop();
    }
    apply {
        if (sm.parser_error != error.NoError) { drop(); }
        else if (h.query.isValid() && h.query.port < 4) {
            if (h.query.op == 0) { query_route.apply(); }
            else if (h.query.op == 1) { query_return.apply(); }
            else { drop(); }
        } else if (m.data == 1 && h.ip.ttl > 1) {
            destination.apply();
            if (sm.egress_spec != 511) { first_hop.apply(); }
            if (sm.egress_spec != 511) { h.ip.ttl = h.ip.ttl - 1; }
        } else { drop(); }
    }
}
control MyEgress(inout headers h, inout metadata m, inout standard_metadata_t sm) {
    // Count data frames actually reaching egress; exclude queries and ARP.
    apply {
        if (m.data == 1) {
            bit<64> count;
            @atomic {
                port_bytes.read(count, (bit<32>)sm.egress_port);
                port_bytes.write((bit<32>)sm.egress_port,
                                        count + (bit<64>)sm.packet_length);
            }
        }
    }
}
control Checksum(inout headers h, inout metadata m) {
    apply {
        update_checksum(h.ip.isValid(),
            {h.ip.version, h.ip.ihl, h.ip.tos, h.ip.len, h.ip.id, h.ip.flags,
             h.ip.offset, h.ip.ttl, h.ip.protocol, h.ip.src, h.ip.dst},
            h.ip.checksum, HashAlgorithm.csum16);
    }
}
control Deparse(packet_out p, in headers h) {
    apply { p.emit(h.eth); p.emit(h.ip); p.emit(h.udp); p.emit(h.query); }
}
V1Switch(Parse(), Verify(), MyIngress(), MyEgress(), Checksum(), Deparse()) main;
