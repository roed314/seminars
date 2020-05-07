from seminars import db
from seminars.toggle import toggle, tritoggle

class WebTopic(object):
    # A topic has an identifier, a name for displaying and a list of children
    def __init__(self, id, name):
        self.id = id
        self.name = name
        # the following are filled in by TopicDAG __init__
        self.children = []
        self.parents = []

class TopicDAG(object):
    def __init__(self):
        self.by_id = {}
        def sort_key(x):
            return x.name.lower()
        for rec in db.new_topics.search():
            self.by_id[rec["id"]] = topic = WebTopic(rec["id"], rec["name"])
            topic.children = rec["children"]
        for topic in self.by_id.values():
            for cid in topic.children:
                self.by_id[cid].parents.append(topic)
        for topic in self.by_id.values():
            topic.children = [self.by_id[cid] for cid in topic.children]
            topic.children.sort(key=sort_key)
            topic.parents.sort(key=sort_key)
        self.subjects = sorted((topic for topic in self.by_id.values() if not topic.parents), key=sort_key)

    def _link(self, topic_id=None, counts={}):
        if topic_id is None:
            tid = name = "topic"
            name = "topic"
            onclick = "toggleFilterView(this.id)"
        else:
            tid = topic_id
            topic = self.by_id[tid]
            name = topic.name
            if not topic.children:
                return name
            onclick = "toggleTopicView('%s')" % topic_id
        count = counts.get(topic_id, 0)
        count = (" (%s)" % count) if count else ""
        return '<a id="%s-filter-btn" class="likeknowl" onclick="%s; return false;">%s</a>%s' % (tid, onclick, name, count)

    def _toggle(self, topic_id=None):
        if topic_id is None:
            tid = "topic"
            tclass = toggle
            onchange = 'toggleFilters(this.id);'
        else:
            tid = topic_id
            topic = self.by_id[tid]
            tclass = tritoggle if topic.children else toggle
            onchange = "toggleTopic('%s');" % topic_id
        return tclass(tid, "", onchange=onchange)

    def filter_link(self, topic_id=None, counts={}):
        return "<td>%s</td><td>%s</td>" % (self._toggle(topic_id), self._link(topic_id, counts))

    def link_pair(self, topic_id=None, counts={}, colclass=""):
        return """<div class="topic_toggle col%s">
  <table><tr>%s</tr></table>
</div>""" % self.filter_link(colclass, topic_id, counts)

    def filter_pane(self, topic_id=None, counts={}):
        if topic_id is None:
            tid = "topic"
            topics = self.subjects
        else:
            tid = topic_id
            topics = self.by_id[tid].children
        mlen = max(len(topic.name for topic in topics))
        # The following are guesses that haven't been tuned.
        if mlen > 50:
            cols = 1
        elif mlen > 35:
            cols = 2
        elif mlen > 25:
            cols = 3
        elif mlen > 16:
            cols = 4
        elif mlen > 10:
            cols = 5
        else:
            cols = 6
        return """
<div id="%s-pane" class="filter-menu topic-pane">
%s
</div>""" % (tid, "\n".join(self.link_pair(topic.id, counts, "colcnt%s" % cols) for topic in topics))

topic_dag = TopicDAG()
