from lmfdb.utils.search_boxes import SearchBox


def toggle(tglid, value, checked=False, classes="", onchange="", name=""):
    if classes:
        classes += " "
    return """
<input type="checkbox" class="{classes}tgl tgl-light" value="{value}" id="{tglid}" onchange="{onchange}" name="{name}" {checked}>
<label class="tgl-btn" for="{tglid}"></label>
""".format(
        tglid=tglid, value=value, checked="checked" if checked else "", classes=classes, onchange=onchange, name=name,
    )


def tritoggle(tglid, value, position=-1, classes="", onchange="", name=""):
    # FIXME
    return toggle(tglid, value, checked=(position==1), classes=classes, onchange=onchange, name=name)


class Toggle(SearchBox):
    def _input(self, info=None):
        main = toggle(
            tglid="toggle_%s" % self.name,
            name=self.name,
            value="yes",
            checked=info is not None and info.get(self.name, False),
        )
        return '<span style="display: inline-block">%s</span>' % (main,)


