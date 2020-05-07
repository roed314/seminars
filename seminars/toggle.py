def toggle(tglid, value, checked=False, classes="", onchange="", name=""):
    if classes:
        classes += " "
    return """
<input
    type="checkbox"
    class="{classes}tgl tgl-light"
    value="{value}"
    id="{tglid}"
    onchange="{onchange}"
    name="{name}"
    {checked}
    ></input>
<label class="tgl-btn" for="{tglid}"></label>
""".format(
        tglid=tglid,
        value=value,
        checked="checked" if checked else "",
        classes=" " + classes if classes else "",
        onchange=onchange,
        name=name,
    )


def toggle3way(tglid, value, classes="", onchange="", name=""):
    if classes:
        classes += " "
    return """
<input
    class="{classes}tgl tgl-light"
    value="{value}" id="{tglid}"
    onchange="{onchange}"
    name="{name}"
    ></input>
<label
    class="tgl-btn"
    for="{tglid}"
    onclick="this.control.value = ((parseInt(this.control.value) + 2)%3) - 1;this.control.dataset.chosen=this.control.value;this.control.onchange();"
    >
</label>
""".format(
        tglid=tglid,
        value=value,
        classes=" " + classes if classes else "",
        onchange=onchange,
        name=name,
    )
