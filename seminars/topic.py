from seminars import db
from .toggle import toggle, toggle3way
from .utils import num_columns
from flask import request
from collections import defaultdict, Counter


class WebTopic(object):
    # A topic has an identifier, a name for displaying and a list of children
    def __init__(self, id, name):
        self.id = id
        self.name = name
        # the following are filled in by TopicDAG __init__
        self.children = []
        self.parents = []

    @property
    def ancestors(self):
        if not self.parents:
            return []
        else:
            return sorted(set([elt.id for elt in self.parents] + sum([elt.ancestors for elt in self.parents], [])))

    def json(self, selected=[]):
        return {
            'text': self.name,
            'li_attr': {'vertex': self.id},
            'state': {'opened': int(self.id in selected),
                      'selected': int(self.id in selected)
                      },
            'children': [ elt.json(selected) for elt in self.children ]
        }



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
        self.subjects = sorted(
            (topic for topic in self.by_id.values() if not topic.parents), key=sort_key
        )

    def leaves(self, topic_list):
        """
        Returns the elements in the topic list that don't have children in the topic list

        INPUT:

        - ``topic_list`` -- a list of topic ids

        OUTPUT:

        The names of topics with no children also in the list
        """
        leaves = []
        for topic in topic_list:
            topic = self.by_id[topic]
            if all(child.id not in topic_list for child in topic.children):
                leaves.append(topic.name)
        return leaves

    def port_cookie(self):
        cur_cookie = request.cookies.get("topics", "")
        topics = []
        for elt in cur_cookie.split(","):
            if "_" in elt:
                sub, top = elt.split("_", 1)
                if sub in self.by_id:
                    topics.append(sub)
                if elt in self.by_id:
                    topics.append(elt)
        return ",".join("%s:1"%elt for elt in topics)

    def read_cookie(self):
        res = defaultdict(lambda:-1)
        if request.cookies.get("topics", ""):
            # old key
            for elt in request.cookies.get("topics", "").split(","):
                if '_' in elt:
                    sub, top = elt.split("_", 1)
                    if sub in self.by_id:
                        res[sub] = 1
                    if elt in self.by_id:
                        res[elt] = 1  # full topic
            # FIXME we need to trigger deletion of the cookie  when building the response
            # and setting the new topics_dict cookie
        for elt in request.cookies.get("topics_dict", "").split(","):
            if ':' in elt:
                key, val = elt.split(":", 1)
                try:
                    val = int(val)
                    if val in [-1, 0, 1] and key in self.by_id:
                        res[key] = val
                except ValueError:
                    pass
        res[None] = 1 if request.cookies.get('filter_topic', '-1') == '1' else -1
        return res

    def _link(self, parent_id="root", topic_id=None, counts={}, duplicate_ctr=None):
        if topic_id is None:
            fullid = name = "topic"
            onclick = "toggleFilterView(this.id)"
            count = ""
            classes = "likeknowl root-tlink"
        else:
            topic = self.by_id[topic_id]
            name = topic.name
            count = counts.get(topic_id, 0)
            count = (" (%s)" % count) if count else ""
            ancestors = ["sub_" + elt for elt in topic.ancestors]
            if not topic.children:
                classes = " ".join(ancestors)
                return '<span class="{0}">{1}</span>'.format(classes, name + count)
            onclick = "toggleTopicView('%s', '%s', '%s')" % (parent_id, topic_id, duplicate_ctr[topic_id])
            classes = " ".join(["likeknowl", parent_id+"-tlink"] + ancestors)
            fullid = "--".join([parent_id, topic_id, str(duplicate_ctr[topic_id])])
        return '<a id="{0}-filter-btn" class="{1}" onclick="{2}; return false;">{3}</a>{4}'.format(
            fullid, classes, onclick, name, count
        )

    def _toggle(self, parent_id="root", topic_id=None, cookie=None, duplicate_ctr=None):
        if cookie is None:
            cookie = self.read_cookie()
        kwds = {}
        if topic_id is None:
            tid = "topic"
            tclass = toggle
            onchange = "toggleFilters(this.id);"
        else:
            tid = "--".join([parent_id, topic_id, str(duplicate_ctr[topic_id])])
            topic = self.by_id[topic_id]
            if topic.children:
                tclass = toggle3way
            else:
                tclass = toggle
            onchange = "toggleTopicDAG(this.id);"
            kwds["classes"] = " ".join([topic_id, "sub_topic"] + ["sub_" + elt for elt in topic.ancestors])
            if cookie[parent_id] != 0 and parent_id != "topic":
                kwds["classes"] += " disabled"
            kwds["name"] = topic_id


        return tclass(tid, value=cookie[topic_id], onchange=onchange, **kwds)

    def filter_link(self, parent_id="root", topic_id=None, counts={}, cookie=None, duplicate_ctr=None):
        padding = ' class="fknowl"' if topic_id is None else ''
        return "<td>%s</td><td%s>%s</td>" % (
            self._toggle(parent_id, topic_id, cookie, duplicate_ctr),
            padding,
            self._link(parent_id, topic_id, counts, duplicate_ctr),
        )

    def link_pair(self, parent_id="root", topic_id=None, counts={}, cols=1, cookie=None, duplicate_ctr=None):
        return """
<div class="toggle_wrap col{0}">
<div class="toggle_pair">
  <table><tr>{1}</tr></table>
</div>
</div>""".format(
            cols, self.filter_link(parent_id, topic_id, counts, cookie, duplicate_ctr)
        )

    def filter_pane(self, parent_id="root", topic_id=None, counts={}, cookie=None, duplicate_ctr=None):
        if cookie is None:
            cookie = self.read_cookie()
        if topic_id is None:
            tid = "topic"
            topics = self.subjects
        else:
            tid = topic_id
            topics = self.by_id[tid].children
        if duplicate_ctr is None:
            duplicate_ctr = Counter()
        cols = num_columns([topic.name for topic in topics])
        divs = []
        delay = []
        for i, topic in enumerate(topics, 1):
            duplicate_ctr[topic.id] += 1
            link = self.link_pair(tid, topic.id, counts, cols, cookie, duplicate_ctr)
            divs.append(link)
            if topic.children:
                filter_pane = self.filter_pane(tid, topic.id, counts, cookie, duplicate_ctr)
                delay.append(filter_pane)
            if i % cols == 0 or i == len(topics):
                divs.extend(delay)
                delay = []
        return """
<div id="{0}--{1}--{2}-pane" class="filter-menu {0}-subpane" style="display:none;">
{3}
</div>""".format(
            parent_id,
            tid,
            duplicate_ctr[tid],
            "\n".join(divs),
       )

    def json(self, selected=[]):
        return [elt.json(selected) for elt in self.subjects]




topic_dag = TopicDAG()
