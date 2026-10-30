#!/usr/bin/env python3
"""Exact-build static check for existing PlayMaker GUI actions (no game writes)."""
from __future__ import annotations
import argparse
import hashlib
import json
import struct
from pathlib import Path
from analyze_ps4_il2cpp_pipeline import parse_metadata_v23
from inspect_aot_registration import NativeImage

MODULE_HASH = '0159ff61c99d25c8f0a821070e3d8b24aff58dbbe5429b8f29561f9960d02969'
METADATA_HASH = '238c400de31e28ed4f7f14e7781ea3b33de0d0bd6964ded680d78fce1d85a6c3'
METHOD_TABLE = 0x0316F8C0
SPEC = {
    'GUIBox':0x02383880,
    'GUILabel':0x02384A20,
    'GUIButton':0x02383D30,
    'GUILayoutBox':0x02386590,
    'GUILayoutLabel':0x02388790,
    'GUILayoutButton':0x02386870,
    'GUILayoutToggle':0x02389640,
}
# The original title also compiles related event/input action callbacks.
# Their presence does NOT establish a DS4/Rewired binding.
INPUT_ACTION_SPEC = {
    'GetButtonDown':('OnUpdate', 0x025374D0, 32),
    'GetKeyDown':('OnUpdate', 0x0253EA50, 32),
    'EnableGUI':('OnEnter', 0x023D7FE0, 30),
    'SendEvent':('OnEnter', 0x023405A0, 30),
}
# VA of call instruction -> verified link VA destination.
BUTTON_EDGES = {
    0x02383DF6:0x019BE750,  # GUI.Button
    0x02383E1E:0x011172B0,  # Fsm.Event
    0x023869D6:0x019CF470,  # GUILayout.Button
    0x02386A58:0x011172B0,  # Fsm.Event
}


def check_edges(read, edges=BUTTON_EDGES):
    result=[]
    for site,target in edges.items():
        code=read(site,5)
        if len(code)!=5 or code[0]!=0xE8 or site+5+struct.unpack('<i',code[1:])[0]!=target:
            raise ValueError('unexpected native button/event call at %s'%hex(site))
        result.append({'site':hex(site),'target':hex(target)})
    return result


def inspect(module:bytes, metadata:bytes):
    if hashlib.sha256(module).hexdigest()!=MODULE_HASH:
        raise ValueError('wrong IL2CPP module')
    if hashlib.sha256(metadata).hexdigest()!=METADATA_HASH:
        raise ValueError('wrong global metadata')
    meta=parse_metadata_v23(metadata)
    image=NativeImage(module)
    result={}
    for name, expected in SPEC.items():
        full='HutongGames.PlayMaker.Actions.'+name
        owners=[typ for typ in meta.types if typ.full_name==full]
        if len(owners)!=1:
            raise ValueError('missing action type: '+full)
        methods=[m for m in meta.methods_named(owners[0],'OnGUI') if m.method_index>=0]
        if len(methods)!=1:
            raise ValueError('missing/ambiguous OnGUI: '+full)
        m=methods[0]
        va=struct.unpack('<Q',image.read(METHOD_TABLE+m.method_index*8,8))[0]
        offset,_=meta.sections['methods']
        slot=struct.unpack_from('<H',metadata,offset+56*m.definition_index+52)[0]
        if va!=expected or not image.executable(va) or slot!=33:
            raise ValueError('OnGUI pointer/slot mismatch: '+full)
        result[name]={'type_definition':owners[0].index,'link_va':hex(va),'virtual_slot':slot}
    input_actions={}
    for name,(callback,expected,expected_slot) in INPUT_ACTION_SPEC.items():
        full='HutongGames.PlayMaker.Actions.'+name
        owner=[t for t in meta.types if t.full_name==full]
        if len(owner)!=1:
            raise ValueError('missing input/event action: '+full)
        defs=[m for m in meta.methods_named(owner[0],callback) if m.method_index>=0]
        if len(defs)!=1:
            raise ValueError('missing action method: '+name+'.'+callback)
        m=defs[0]
        va=struct.unpack('<Q',image.read(METHOD_TABLE+m.method_index*8,8))[0]
        pos,_=meta.sections['methods']
        slot=struct.unpack_from('<H',metadata,pos+56*m.definition_index+52)[0]
        if va!=expected or slot!=expected_slot or not image.executable(va):
            raise ValueError('action method mismatch: '+name+'.'+callback)
        input_actions[name]={'callback':callback,'link_va':hex(va),'virtual_slot':slot}
    return {
        'precompiled_input_event_actions':input_actions,
        'title':'The Forest PS4 CUSA12398 v1.15',
        'precompiled_gui_actions':result,
        'button_to_native_gui_and_fsm_event_edges':check_edges(image.read),
        'limitations':'Static compiled methods only; no custom FSM, callback subscription, or PRX registered',
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--module',type=Path,required=True)
    p.add_argument('--metadata',type=Path,required=True)
    p.add_argument('--output',type=Path)
    a=p.parse_args()
    try:
        output=json.dumps(inspect(a.module.read_bytes(),a.metadata.read_bytes()),indent=2)+'\n'
        if a.output:
            a.output.parent.mkdir(parents=True,exist_ok=True)
            a.output.write_text(output)
        else:
            print(output,end='')
    except (ValueError,OSError,struct.error) as exc:
        p.exit(2,'gui-aot-audit: %s\n'%exc)


if __name__=='__main__':
    main()
