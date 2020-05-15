
def toggle(tglid, value, classes="", onchange="", name=""):
    if classes:
        classes += " "
    assert value in [-1, 1]
    return """
<input
    class="{classes}tgl tgl-light tgl2way"
    value="{value}"
    data-chosen="{value}"
    id="{tglid}"
    onchange="{onchange}"
    name="{name}"
    ></input>
<label class="{classes}tgl-btn"
       for="{tglid}"
        onclick="this.control.value = -parseInt(this.control.value);this.control.dataset.chosen=this.control.value;this.control.dispatchEvent(new Event('change'));"
       ></label>
""".format(
        tglid=tglid,
        value=value,
        classes=classes,
        onchange=onchange,
        name=name,
    )


def toggle3way(tglid, value, classes="", onchange="", name=""):
    if classes:
        classes += " "
    assert value in [-1, 0, 1]
    return """
<input
    class="{classes}tgl tgl-light tgl3way"
    value="{value}" id="{tglid}"
    data-chosen="{value}"
    onchange="{onchange}"
    name="{name}"
    ></input>
<label
    class="{classes}tgl-btn"
    for="{tglid}"
    onclick="this.control.value = ((parseInt(this.control.value) + 2)%3) -1;this.control.dataset.chosen=this.control.value;this.control.dispatchEvent(new Event('change'));"
    >
</label>
""".format(
        tglid=tglid,
        value=value,
        classes=classes,
        onchange=onchange,
        name=name,
    )
