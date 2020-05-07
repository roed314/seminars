from seminars import db
from seminars.toggle import toggle, toggle3way

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
            self.by_id[rec["topic_id"]] = topic = WebTopic(rec["topic_id"], rec["name"])
            topic.children = rec["children"]
        for topic in self.by_id.values():
            for cid in topic.children:
                self.by_id[cid].parents.append(topic)
        for topic in self.by_id.values():
            topic.children = [self.by_id[cid] for cid in topic.children]
            topic.children.sort(key=sort_key)
            topic.parents.sort(key=sort_key)
        self.subjects = sorted((topic for topic in self.by_id.values() if not topic.parents), key=sort_key)

    def _link(self, parent_id="topic", topic_id=None, counts={}):
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
            onclick = "toggleTopicView('%s', '%s')" % (parent_id, tid)
        count = counts.get(topic_id, 0)
        count = (" (%s)" % count) if count else ""
        return '<a id="{0}-filter-btn" class="likeknowl {1}-tlink" onclick="{2}; return false;">{3}</a>{4}'.format(tid, parent_id, onclick, name, count)

    def _toggle(self, topic_id=None):
        if topic_id is None:
            tid = "topic"
            tclass = toggle
            onchange = 'toggleFilters(this.id);'
        else:
            tid = topic_id
            topic = self.by_id[tid]
            tclass = toggle3way if topic.children else toggle
            onchange = "toggleTopic('%s');" % topic_id
        return tclass(tid, "", onchange=onchange)

    def filter_link(self, parent_id="topic", topic_id=None, counts={}):
        return "<td>%s</td><td>%s</td>" % (self._toggle(topic_id), self._link(parent_id, topic_id, counts))

    def link_pair(self, parent_id="topic", topic_id=None, counts={}, cols=1):
        return """<div class="topic_toggle col{0}">
  <table><tr>{1}</tr></table>
</div>""".format(cols, self.filter_link(parent_id, topic_id, counts))

    def filter_pane(self, parent_id="topic", topic_id=None, counts={}):
        if topic_id is None:
            tid = "topic"
            topics = self.subjects
        else:
            tid = topic_id
            topics = self.by_id[tid].children
        childpanes = [topic.id for topic in topics if topic.children]
        mlen = max(len(topic.name) for topic in topics)
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
<div id="{0}-{1}-pane" class="filter-menu {0}-subpane" style="display:none;">
{2}
{3}
</div>""".format(parent_id,
                 tid,
                 "\n".join(self.link_pair(tid, topic.id, counts, cols) for topic in topics),
                 "\n".join(self.filter_pane(tid, child, counts) for child in childpanes))

topic_dag = TopicDAG()
