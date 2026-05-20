from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent
PEAK_BUCK = ROOT / "buck_48v_12v_dual_loop.plecs"
ANALOG_BUCK = Path(
    r"D:\Plexim\PLECS 4.7 (64 bit)\demos\buck_converter_with_analog_controls\buck_converter_with_analog_controls.plecs"
)
OUT = ROOT / "buck_48v_12v_dual_pi_built.plecs"


def find_block(text: str, keyword: str, block_type: str = "Component") -> str:
    idx = text.index(keyword)
    start = text.rfind(f"{block_type} {{", 0, idx)
    if start < 0:
        raise ValueError(f"Could not find {block_type} start for {keyword!r}")
    depth = 0
    i = start
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
        i += 1
    raise ValueError(f"Unclosed block for {keyword!r}")


def replace_param(block: str, variable: str, value: str) -> str:
    marker = f'Variable      "{variable}"'
    idx = block.index(marker)
    match = re.search(r'\n(\s*)Value\s+"[^"]*"', block[idx:])
    if not match:
        raise ValueError(f"Could not find Value line for {variable!r}")
    val_idx = idx + match.start()
    old_line = match.group(0)
    indent = match.group(1)
    new_line = f'\n{indent}Value         "{value}"'
    return block[:val_idx] + new_line + block[val_idx + len(old_line) :]


def replace_component(text: str, name: str, new_block: str) -> str:
    old = find_block(text, f'Name          "{name}"')
    return text.replace(old, new_block, 1)


def delete_component(text: str, name: str) -> str:
    old = find_block(text, f'Name          "{name}"')
    return text.replace(old + "\n", "", 1)


def insert_before_first_connection(text: str, block: str) -> str:
    pos = text.index("    Connection {")
    return text[:pos] + block.rstrip() + "\n" + text[pos:]


def make_output(name: str, index: int, x: int, y: int) -> str:
    return f'''    Component {{
      Type          Output
      Name          "{name}"
      Show          on
      Position      [{x}, {y}]
      Direction     right
      Flipped       off
      LabelPosition south
      Parameter {{
        Variable      "Index"
        Value         "{index}"
        Show          on
      }}
      Parameter {{
        Variable      "Width"
        Value         "-1"
        Show          off
      }}
    }}
'''


def main() -> None:
    text = PEAK_BUCK.read_text(encoding="utf-8")
    analog = ANALOG_BUCK.read_text(encoding="utf-8")

    text = text.replace('Name          "buck_converter_with_peak_current_control"', 'Name          "buck_48v_12v_dual_pi_built"', 1)
    text = text.replace('TimeSpan      "10e-3"', 'TimeSpan      "20e-3"', 1)
    text = text.replace('MaxStep       "1"', 'MaxStep       "1e-6"', 1)
    text = text.replace('InitializationCommands ""', 'InitializationCommands "Vin=48; Vref_cmd=12; Rload=6; fsw=100e3;"', 1)

    for comp_name, variable, value in [
        ("V_dc", "V", "48"),
        ("L1", "L", "100e-6"),
        ("C1", "C", "220e-6"),
        ("R", "R", "6"),
        ("R1", "R", "6"),
        ("Vref", "Value", "12"),
    ]:
        block = find_block(text, f'Name          "{comp_name}"')
        text = text.replace(block, replace_param(block, variable, value), 1)

    text = delete_component(text, "Peak Current\\nController")

    vpi = find_block(text, 'Name          "PI Voltage\\nController"')
    vpi = vpi.replace('Name          "PI Voltage\\nController"', 'Name          "Voltage PI\\nController"', 1)
    vpi = replace_param(vpi, "kp", "0.35")
    vpi = replace_param(vpi, "ki", "2200")
    vpi = replace_param(vpi, "fs", "100e3")
    text = replace_component(text, "PI Voltage\\nController", vpi)

    cpi = vpi.replace('Name          "Voltage PI\\nController"', 'Name          "Current PI\\nController"', 1)
    cpi = cpi.replace("Position      [155, 110]", "Position      [220, 370]", 1)
    cpi = replace_param(cpi, "kp", "0.08")
    cpi = replace_param(cpi, "ki", "18000")
    cpi = replace_param(cpi, "fs", "100e3")

    sum_block = find_block(text, 'Name          "Sum"')
    isum = sum_block.replace('Name          "Sum"', 'Name          "Current Sum"', 1)
    isum = isum.replace("Position      [90, 110]", "Position      [165, 370]", 1)

    sat = find_block(analog, 'Name          "Saturation"')
    sat = sat.replace('Name          "Saturation"', 'Name          "Duty Limit"', 1)
    sat = sat.replace("Position      [105, 370]", "Position      [105, 370]", 1)
    sat = replace_param(sat, "UpperLimit", "0.92")
    sat = replace_param(sat, "LowerLimit", "0.02")

    carrier = find_block(analog, 'Name          "Sawtooth\\nGenerator"')
    carrier = carrier.replace('Name          "Sawtooth\\nGenerator"', 'Name          "PWM Carrier"', 1)
    carrier = carrier.replace("Position      [105, 310]", "Position      [105, 310]", 1)
    carrier = replace_param(carrier, "f", "100e3")

    comp = find_block(analog, 'Name          "Relational\\nOperator"')
    comp = comp.replace('Name          "Relational\\nOperator"', 'Name          "PWM Comparator"', 1)
    comp = comp.replace("Position      [45, 365]", "Position      [45, 365]", 1)

    additions = (
        cpi
        + "\n"
        + isum
        + "\n"
        + sat
        + "\n"
        + carrier
        + "\n"
        + comp
        + "\n"
        + make_output("Vout", 1, 610, 285)
        + make_output("IL", 2, 610, 315)
        + make_output("Duty", 3, 610, 345)
    )
    text = insert_before_first_connection(text, additions)

    replacements = {
        '''    Connection {
      Type          Signal
      SrcComponent  "Peak Current\\nController"
      SrcTerminal   3
      Points        [305, 100]
      DstComponent  "T1"
      DstTerminal   3
    }
''': '''    Connection {
      Type          Signal
      SrcComponent  "PWM Comparator"
      SrcTerminal   3
      Points        [20, 365; 20, 145; 305, 145]
      DstComponent  "T1"
      DstTerminal   3
    }
''',
        '''    Connection {
      Type          Signal
      SrcComponent  "PI Voltage\\nController"
      SrcTerminal   1
      DstComponent  "Peak Current\\nController"
      DstTerminal   2
    }
''': '''    Connection {
      Type          Signal
      SrcComponent  "Voltage PI\\nController"
      SrcTerminal   1
      DstComponent  "Current Sum"
      DstTerminal   2
    }
''',
        '''    Connection {
      Type          Signal
      SrcComponent  "Sum"
      SrcTerminal   1
      DstComponent  "PI Voltage\\nController"
      DstTerminal   2
    }
''': '''    Connection {
      Type          Signal
      SrcComponent  "Sum"
      SrcTerminal   1
      DstComponent  "Voltage PI\\nController"
      DstTerminal   2
    }
''',
    }
    for old, new in replacements.items():
        if old not in text:
            raise ValueError(f"Missing expected connection block:\n{old}")
        text = text.replace(old, new, 1)

    am_old = '''    Connection {
      Type          Signal
      SrcComponent  "Am1"
      SrcTerminal   3
      Points        [405, 65]
      Branch {
        DstComponent  "Scope"
        DstTerminal   2
      }
      Branch {
        Points        [215, 65; 215, 90]
        DstComponent  "Peak Current\\nController"
        DstTerminal   1
      }
    }
'''
    am_new = '''    Connection {
      Type          Signal
      SrcComponent  "Am1"
      SrcTerminal   3
      Points        [405, 65]
      Branch {
        DstComponent  "Scope"
        DstTerminal   2
      }
      Branch {
        Points        [165, 65; 165, 350]
        DstComponent  "Current Sum"
        DstTerminal   3
      }
      Branch {
        DstComponent  "IL"
        DstTerminal   1
      }
    }
'''
    text = text.replace(am_old, am_new, 1)

    vm_old = '''    Connection {
      Type          Signal
      SrcComponent  "Vm1"
      SrcTerminal   3
      Points        [525, 220; 525, 55]
      Branch {
        DstComponent  "Scope"
        DstTerminal   1
      }
      Branch {
        Points        [90, 55]
        DstComponent  "Sum"
        DstTerminal   3
      }
    }
'''
    vm_new = '''    Connection {
      Type          Signal
      SrcComponent  "Vm1"
      SrcTerminal   3
      Points        [525, 220; 525, 55]
      Branch {
        DstComponent  "Scope"
        DstTerminal   1
      }
      Branch {
        Points        [90, 55]
        DstComponent  "Sum"
        DstTerminal   3
      }
      Branch {
        DstComponent  "Vout"
        DstTerminal   1
      }
    }
'''
    text = text.replace(vm_old, vm_new, 1)

    extra_connections = '''    Connection {
      Type          Signal
      SrcComponent  "Current Sum"
      SrcTerminal   1
      DstComponent  "Current PI\\nController"
      DstTerminal   2
    }
    Connection {
      Type          Signal
      SrcComponent  "Current PI\\nController"
      SrcTerminal   1
      DstComponent  "Duty Limit"
      DstTerminal   1
    }
    Connection {
      Type          Signal
      SrcComponent  "PWM Carrier"
      SrcTerminal   1
      Points        [75, 310]
      DstComponent  "PWM Comparator"
      DstTerminal   1
    }
    Connection {
      Type          Signal
      SrcComponent  "Duty Limit"
      SrcTerminal   2
      Branch {
        DstComponent  "PWM Comparator"
        DstTerminal   2
      }
      Branch {
        DstComponent  "Duty"
        DstTerminal   1
      }
    }
'''
    anno_pos = text.index("    Annotation {")
    text = text[:anno_pos] + extra_connections + text[anno_pos:]

    text = text.replace("Current-controlled buck", "48 V to 12 V dual-PI current-controlled buck", 1)
    text = text.replace('DemoSignature "O/0Ve/xkLebNm0OGmyHriaRhyIX4Q2e2jJC8OHOEZHE="\n', "")

    OUT.write_text(text, encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    main()
