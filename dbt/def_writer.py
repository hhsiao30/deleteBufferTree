from .def_parser import Design

def _comp_line(c) -> str:
    if c.tail:
        return f"- {c.name} {c.cell} {c.tail} ;"
    return f"- {c.name} {c.cell} ;"

def _net_lines(n) -> str:
    parts = [f"- {n.name}"]
    parts += [f"  ( {a} {b} )" for a, b in n.terms]
    if n.props:
        parts.append(f"  {n.props}")
    return "\n".join(parts) + "\n ;"

def write_def(d: Design, path: str) -> None:
    with open(path, "w") as f:
        f.write(d.header)
        f.write(f"COMPONENTS {len(d.components)} ;\n")
        for c in d.components.values():
            f.write(_comp_line(c) + "\n")
        f.write("END COMPONENTS\n")
        f.write(d.mid)
        f.write(f"NETS {len(d.nets)} ;\n")
        for n in d.nets.values():
            f.write(_net_lines(n) + "\n")
        f.write("END NETS\n")
        f.write(d.footer)
