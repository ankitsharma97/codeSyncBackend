"""Minimal codec for the y-protocols awareness message.

The server never interprets awareness state; it only needs the client ids and
clocks so it can replay the current peers to a newcomer and announce a peer's
removal when its socket drops.
"""
import json

from pycrdt import Decoder, YMessageType, create_awareness_message, write_var_uint


def parse(message):
    """Return [(client_id, clock, state_json)] from a full awareness message."""
    payload = Decoder(message[1:]).read_message()
    decoder = Decoder(payload)
    return [
        (decoder.read_var_uint(), decoder.read_var_uint(), decoder.read_var_string())
        for _ in range(decoder.read_var_uint())
    ]


def encode(entries):
    """Build a full awareness message from [(client_id, clock, state_json)]."""
    out = [write_var_uint(len(entries))]
    for client_id, clock, state in entries:
        raw = state.encode()
        out += [write_var_uint(client_id), write_var_uint(clock), write_var_uint(len(raw)), raw]
    return create_awareness_message(b''.join(out))


def removal(client_id, clock):
    return encode([(client_id, clock + 1, json.dumps(None))])


def is_awareness(message):
    return message[0] == YMessageType.AWARENESS
