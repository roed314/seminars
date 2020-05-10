import iso639
from seminars import db
from seminars.toggle import toggle
from flask import request

class Languages(object):
    def __init__(self):
        def simplify_language_name(name):
            name = name.split(";")[0]
            if "(" in name:
                name = name[: name.find("(") - 1]
            return name

        self._data = {
            lang["iso639_1"]: simplify_language_name(lang["name"])
            for lang in iso639.data
            if lang["iso639_1"]
        }

    def show(self, code):
        return self._data.get(code, "Unknown language")

    def clean(self, code):
        if code not in self._data:
            return "en"
        else:
            return code

    def used(self):
        return sorted(db.talks.distinct("language"))

    def js_options(self):
        items = ",\n".join('  {\n    label: `%s`,\n    value: `%s`\n  }' % (name, code) for (code, name) in self._data.items())
        return "const langOptions = [\n%s\n];" % (items)

    def search_options(self):
        return ([("", ""), ("en", "English")] +
                [(code, self._data[code]) for code in self.used() if code != "en"])

    def _link(self, code=None, counts={}):
        if code is None:
            return '<a id="language-filter-btn" class="likeknowl" onclick="toggleFilterView(this.id); return false;">language</a>'
        else:
            count = counts.get(code)
            count = (" (%s)" % count) if count else ""
            return self.show(code) + count

    def _toggle(self, code=None):
        if code is None:
            code = "language"
            onchange = 'toggleFilters(this.id);'
        else:
            onchange = 'toggleLanguage(this.id);'
        return toggle(code,
                      value = 1 if request.cookies.get('filter_language', '0') != '0' else -1,
                      onchange=onchange)

    def filter_link(self, code=None, counts={}):
        padding = ' style="padding-right: 2em;"' if code is None else ''
        return "<td>%s</td><td%s>%s</td>" % (self._toggle(code), padding, self._link(code, counts))

    def link_pair(self, code=None, counts={}, cols=6):
        return """<div class="toggle_pair col{0}">
  <table><tr>{1}</tr></table>
</div>""".format(cols, self.filter_link(code, counts))

    def filter_pane(self, counts={}):
        langs = sorted(counts, key=lambda x: (-counts[x], self.show(x)))
        return """
<div id="language-filter-menu" class="filter-menu">
{0}
</div>""".format("\n".join(self.link_pair(code, counts) for code in langs))

languages = Languages()