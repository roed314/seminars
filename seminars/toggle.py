def toggle(tglid, value, checked=False, classes="", onchange="", name=""):
    if classes:
        classes += " "
    return """
<input
    type="checkbox"
    class="{classes}tgl tgl-light tgl2way"
    value="{value}"
    id="{tglid}"
    onchange="{onchange}"
    name="{name}"
    {checked}
    ></input>
<label class="{classes}tgl-btn" for="{tglid}"></label>
""".format(
        tglid=tglid,
        value=value,
        checked="checked" if checked else "",
        classes=classes,
        onchange=onchange,
        name=name,
    )


def toggle3way(tglid, value, classes="", onchange="", name=""):
    if classes:
        classes += " "
    assert value in [0, 1, 2]
    return """
<input
    class="{classes}tgl tgl-light tgl3way"
    value="{value}" id="{tglid}"
    onchange="{onchange}"
    name="{name}"
    ></input>
<label
    class="{classes}tgl-btn"
    for="{tglid}"
    onclick="this.control.value = (parseInt(this.control.value) + 1)%3;this.control.dataset.chosen=this.control.value;this.control.onchange();"
    >
</label>
""".format(
        tglid=tglid,
        value=value,
        classes=classes,
        onchange=onchange,
        name=name,
    )
