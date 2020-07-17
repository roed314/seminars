from seminars import db
from .toggle import toggle, toggle3way
from .utils import num_columns
from flask import request
from collections import defaultdict, Counter
from lmfdb.backend.utils import DelayCommit
import re


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

    def add_topics(self, filename, dryrun=False):
        """
        File format: one line for each topic, asterisks to indicate children, tilde for dividing topic id from topic name.
        You can include a topic that already exists in order to add children, and you can include a topic multiple times to get the DAG structure.
        Example:

        chem ~ Chemistry
        * bio_BC ~ biochemistry
        ** bio_EZ ~ enzymology
        bio ~ Biology
        * bio_BC ~ biochemistry
        math_NT ~ number theory
        * math_AR ~ arithmetic geometry
        math_AG ~ algebraic geometry
        * math_AR ~ arithmetic geometry
        """
        existing_topics = dict(self.by_id)
        new_topics = {}
        children = defaultdict(set)
        children.update({tid: set(WT.id for WT in self.by_id[tid].children) for tid in self.by_id})
        update_children = set()
        current_path = []
        with open(filename) as F:
            for line in F:
                m = re.match(r"^([*\s]*)(.*)", line)
                depth = m.group(1).count("*")
                if depth > len(current_path):
                    raise ValueError("Invalid tree structure: can only indent one level at a time")
                content = m.group(2).split("~")
                if len(content) != 2:
                    raise ValueError("You must specify both id and name: %s" % content)
                topic_id = content[0].strip()
                topic_name = content[1].strip()
                current_path = current_path[:depth]
                if topic_id in existing_topics:
                    old_name = existing_topics[topic_id].name
                    if topic_name != old_name:
                        raise ValueError("Inconsistent topic name: %s (new) vs %s (existing)" % (topic_name, old_name))
                else:
                    new_topics[topic_id] = topic_name
                    existing_topics[topic_id] = WebTopic(topic_id, topic_name)
                if current_path:
                    if topic_id not in children[current_path[-1]]:
                        update_children.add(current_path[-1])
                    children[current_path[-1]].add(topic_id)
                current_path.append(topic_id)
        topic_list = [{"topic_id": tid, "name": name, "children": sorted(children[tid])} for (tid, name) in new_topics.items()]
        updates = {tid: sorted(children[tid]) for tid in update_children if tid not in new_topics}
        print("New topics being added:\n  %s" % ("\n  ".join(T["name"] for T in topic_list)))
        print("Child relationships being added:")
        for T in topic_list:
            for C in T["children"]:
                print("  %s -> %s" % (T["name"], existing_topics[C].name))
        for tid, children in updates.items():
            for C in children:
                if C not in self.by_id[tid].children:
                    print("  %s -> %s" % (existing_topics[tid].name, existing_topics[C].name))
        if not dryrun:
            with DelayCommit(db):
                db.new_topics.insert_many(topic_list)
                for tid, children in updates.items():
                    db.new_topics.update({"topic_id": tid}, {"children": children})

    def filtered_topics(self, topic=None):
        cookie = self.read_cookie()
        res = []
        for elt in (self.subjects if topic is None else topic.children):
            if cookie[elt.id] == 1:
                res.append(elt.id)
            elif cookie[elt.id] == 0:
                res.extend(self.filtered_topics(elt))
        return res

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
        return ",".join("%s:1" % elt for elt in topics)

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
            spanclasses = ""
        else:
            topic = self.by_id[topic_id]
            name = topic.name
            count = counts.get(topic_id, 0)
            count = (" (%s)" % count) if count else ""
            ancestors = ["sub_" + elt for elt in topic.ancestors]
            spanclasses = " ".join(ancestors)
            if not topic.children:
                return '<span class="{0}">{1}</span>'.format(spanclasses, name + count)
            onclick = "toggleTopicView('%s', '%s', '%s')" % (parent_id, topic_id, duplicate_ctr[topic_id])
            classes = " ".join(["likeknowl", parent_id+"-tlink"] + ancestors)
            fullid = "--".join([parent_id, topic_id, str(duplicate_ctr[topic_id])])
        return '<a id="{0}-filter-btn" class="{1}" onclick="{2}; return false;">{3}</a><span class="{4}">{5}</span>'.format(
            fullid, classes, onclick, name, spanclasses, count
        )

    def _toggle(self, parent_id="root", topic_id=None, cookie=None, duplicate_ctr=None, disabled=False):
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
            if disabled:
                kwds["classes"] += " disabled"
            kwds["name"] = topic_id


        return tclass(tid, value=cookie[topic_id], onchange=onchange, **kwds)

    def filter_link(self, parent_id="root", topic_id=None, counts={}, cookie=None, duplicate_ctr=None, disabled=False):
        padding = ' class="fknowl"' if topic_id is None else ''
        return "<td>%s</td><td%s>%s</td>" % (
            self._toggle(parent_id, topic_id, cookie, duplicate_ctr, disabled=disabled),
            padding,
            self._link(parent_id, topic_id, counts, duplicate_ctr),
        )

    def link_pair(self, parent_id="root", topic_id=None, counts={}, cols=1, cookie=None, duplicate_ctr=None, disabled=False):
        return """
<div class="toggle_wrap col{0}">
<div class="toggle_pair">
  <table><tr>{1}</tr></table>
</div>
</div>""".format(
            cols, self.filter_link(parent_id, topic_id, counts, cookie, duplicate_ctr, disabled=disabled)
        )

    def filter_pane(self, parent_id="root", topic_id=None, counts={}, cookie=None, duplicate_ctr=None, visible=False, disabled=False):
        if cookie is None:
            cookie = self.read_cookie()
        if topic_id is None:
            tid = "topic"
            topics = self.subjects
            divhelp = '<p style="margin-left: 10px;">Click a 3-way toggle <i>twice</i> to select all subtopics; click on "Filter" for more details.</p>'
        else:
            tid = topic_id
            topics = self.by_id[tid].children
            disabled = disabled or cookie[tid] != 0
            divhelp = ''
        if duplicate_ctr is None:
            duplicate_ctr = Counter()
        cols = num_columns([topic.name for topic in topics])
        divs = []
        delay = []
        for i, topic in enumerate(topics, 1):
            duplicate_ctr[topic.id] += 1
            link = self.link_pair(tid, topic.id, counts, cols, cookie, duplicate_ctr, disabled=disabled)
            divs.append(link)
            if topic.children:
                filter_pane = self.filter_pane(tid, topic.id, counts, cookie, duplicate_ctr, disabled=disabled)
                delay.append(filter_pane)
            if i % cols == 0 or i == len(topics):
                divs.extend(delay)
                delay = []
        return """
<div id="{0}--{1}--{2}-pane" class="filter-menu {0}-subpane" style="display:{4};">
{5}
{3}
</div>""".format(
            parent_id,
            tid,
            duplicate_ctr[tid],
            "\n".join(divs),
            "block" if visible else "none",
            divhelp,
       )

    def json(self, selected=[]):
        return [elt.json(selected) for elt in self.subjects]




topic_dag = TopicDAG()
