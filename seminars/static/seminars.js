// from lmfdb.js,
function cleanSubmit(id)
{
  var myForm = document.getElementById(id);
  var allInputs = myForm.getElementsByTagName('input');
  var allSelects = myForm.getElementsByTagName('select');
  var item, i, n = 0;
  for(i = 0; item = allInputs[i]; i++) {
    if (item.getAttribute('name') ) {
        // Special case count so that we strip the default value
        if (!item.value || (item.getAttribute('name') == 'count' && item.value == 50)) {
        item.setAttribute('name', '');
      } else {
        n++;
      }
    }
  }
  for(i = 0; item = allSelects[i]; i++) {
    if (item.getAttribute('name') ) {
      if (!item.value) {
        item.setAttribute('name', '');
      } else {
        n++;
      }
    }
  }
  if (!n) {
    var all = document.createElement('input');
    all.type='hidden';
    all.name='all';
    all.value='1';
    myForm.appendChild(all);
  }
}


function toggle_time(id) {
    var future = $('#future_talks');
    var past = $('#past_talks');
    if (future.is(":visible"))
    {
        if (id == "toggle_to_past") {
            $('.toggler-nav').toggleClass("toggler-active");
            future.hide();
            past.show();
        }
    } else {
        if (id == "toggle_to_future") {
            $('.toggler-nav').toggleClass("toggler-active");
            past.hide();
            future.show();
        }
    }
}


function setCookie(name,value) {
    if (navigator.cookieEnabled) {
        // our cookies have a 10-year shelf life
        document.cookie = name + "=" + (value || "") + ";Path=/;Max-age=315360000";
    }
}
function getCookie(name) {
    if (navigator.cookieEnabled) {
      var nameEQ = name + "=";
      var ca = document.cookie.split(';');
      for(var i=0;i < ca.length;i++) {
          var c = ca[i];
          while (c.charAt(0)==' ') c = c.substring(1,c.length);
          if (c.indexOf(nameEQ) == 0) return c.substring(nameEQ.length,c.length);
      }
    }
    return null;
}
function eraseCookie(name) {
    document.cookie = name+'=; Max-Age=-99999999;';
}
function addToCookie(item, cookie) {
    var cur_items = getCookie(cookie);
    if (cur_items) {
        cur_items = cur_items + "," + item;
    } else {
        cur_items = item;
    }
    setCookie(cookie, cur_items);
    return cur_items;
}
function removeFromCookie(item, cookie) {
    var cur_items = getCookie(cookie);
    cur_items = cur_items.replace(item, "").replace(",,",",");
    if (cur_items.startsWith(",")) cur_items = cur_items.slice(1);
    if (cur_items.endsWith(",")) cur_items = cur_items.slice(0, -1);
    setCookie(cookie, cur_items);
    return cur_items;
}
function setTopicCookie(topic, value) {
    console.log("setTopicCookie", topic, value);
    var cookie = getCookie("topics_dict");
    if (cookie == null || cookie == "") {
        var cur_items = [];
    } else {
        var cur_items = cookie.split(",");
    }
    var new_item = topic + ":" + value.toString();
    var found = false;
    for (let i=0;i<cur_items.length;i++) {
        if (cur_items[i].startsWith(topic + ":")) {
            cur_items[i] = new_item
            found = true;
            break;
        }
    }
    if (!found) {
        cur_items.push(new_item);
    }
    console.log(cur_items);
    setCookie("topics_dict", cur_items.join(","));
}
function getTopicCookie(topic) {
    var cur_items = getCookie("topics_dict").split(",");
    for (let i=0; i<cur_items.length; i++) {
        if (cur_items[i].startsWith(topic + ":")) {
            return parseInt(cur_items[i].substring(topic.length+1));
        }
    }
    return 0;
}
function getTopicCookieWithValue(value) {
    value = value.toString();
    var cur_items = getCookie("topics_dict").split(",");
    var with_value = [];
    for (var i=0; i<cur_items.length; i++) {
        if (cur_items[i].endsWith(":" + value)) {
            with_value.push(cur_items[i].substring(0, value.length+1));
        }
    }
    return with_value;
}
function setToggle(id, value) {
    var toggle = $('#'+id);
    toggle.val(value)
    toggle.attr('data-chosen', value);
}

function topicFiltering() {
    return $('#topic').val() == "1";
}
function enableTopicFiltering() {
    setCookie("filter_topic", "1");
    setToggle("topic", 1);
    toggleFilters(null);
}
function languageFiltering() {
    return $('#language').val() == "1";
}
function enableLanguageFiltering() {
    setCookie("filter_language", "1");
    setToggle("language", 1);
    toggleFilters(null);
}
function calFiltering() {
    return $('#enable_calendar_filter').val() == "1";
}

function topicFromPair(pairid) {
    return pairid.split("--")[1];
}

function reviseCookies() {
    // This function sets cookies initially if they aren't set and changes them when needed by code changes
    if (getCookie("languages") == null) {
        setCookie("languages", "");
    }
    if (getCookie("topics_dict") == null) {
        cur_topics = getCookie("topics");
        if (cur_topics == null) {
            setCookie("topics_dict", "");
        } else {
            cur_topics = cur_topics.split(",");
            cur_subjects = getCookie("subjects");
            if (cur_subjects == null) {
                cur_subjects = "";
            } else {
                cur_subjects = cur_subjects.split(",");
            }
            cur_topics = cur_subjects.concat(cur_topics);
            cur_topics = cur_topics.map((top) => { return top + ":1" });
            setCookie("topics_dict", cur_topics.join(","));
            eraseCookie("topics");
        }
    }
    var ftypes = ["topic", "language", "calendar", "time", "location"];
    var pm1 = ["-1", "1"];
    for (i=0; i<ftypes.length; i++) {
        if (!(getCookie("filter_"+ftypes[i]) in pm1)) {
            setCookie("filter_"+ftypes[i], "-1");
        }
    }
}

function toggleLanguage(id) {
    var toggle = $("#" + id);
    var toggleval = parseInt(toggle.val());
    console.log(id, toggleval);
    var lang = id.substring(9); // langlink-*
    var talks = $(".talk.lang-" + lang);
    if (toggleval == -1) {
        removeFromCookie(lang, "languages");
        talks.addClass("language-filtered");
        if (languageFiltering()) {
            talks.hide();
            apply_striping();
        }
    } else {
        addToCookie(lang, "languages");
        talks.removeClass("language-filtered");
        if (languageFiltering()) {
            // elements may be filtered by other criteria
            talks = talksToShow(talks);
            talks.show();
            apply_striping();
        }
    }
}

function toggleTopicDAG(togid) {
    var to_show = [];
    var to_hide = [];
    console.log(togid);
    var topic = topicFromPair(togid);
    var toggle = $("#" + togid);
    var toggleval = parseInt(toggle.val());
    console.log(toggleval);
    setTopicCookie(topic, toggleval);
    if (toggleval == 0) {
        $("label.sub_" + topic).css("visibility", "visible");
        $("a.sub_"+topic+",span.sub_"+topic).removeClass("not_toggleable");
        var pane = $("#"+togid+"-pane");
        var is_visible = pane.is(":visible");
        if (!is_visible) {
            var triple = togid.split("--");
            toggleTopicView(triple[0], triple[1], triple[2]);
        }
        // Need to show rows corresponding to sub-topics.
        // We can't just use $("tgl.sub_"+topic).each(),
        // since some 1s may be under -1s.
        var blocking_toggles = [];
        $('input[value="-1"].tgl3way.sub_'+topic).each(function() {
            blocking_toggles.push(topicFromPair(this.id));
        });
        console.log("blocking_toggles", blocking_toggles);
        var show_selector = $('input[value="1"].sub_'+topic);
        for (let i=0; i<blocking_toggles.length; i++) {
            show_selector = show_selector.not(".sub_"+blocking_toggles[i]);
        }
        show_selector.each(function() {
            to_show.push(topicFromPair(this.id));
        });
    } else {
        $("label.sub_" + topic).css("visibility", "hidden");
        if (toggleval == 1) {
            to_show.push(topic);
        } else {
            $("a.sub_"+topic+",span.sub_"+topic).addClass("not_toggleable");
            to_hide.push(topic);
        }
    }
    console.log("show", to_show);
    console.log("hide", to_hide);
    if (to_show.length > 0) {
        var talks = $();
        for (let i=0; i<to_show.length; i++) {
            talks = talks.add(".talk.topic-filtered.topic-" + topic);
        }
        talks.removeClass("topic-filtered");
        if (topicFiltering()) {
            // elements may be filtered by other criteria
            talks = talksToShow(talks);
            talks.show();
            apply_striping();
        }
    }
    if (to_hide.length > 0) {
        var talks = $(".talk.topic-" + topic);
        var cur_topics = getTopicCookieWithValue(1);
        for (let i=0; i<cur_topics.length; i++) {
            talks = talks.not(".topic-" + cur_topics[i]);
        }
        talks.addClass("topic-filtered");
        if (topicFiltering()) {
            talks.hide();
            apply_striping();
        }
    }
}

function toggleTopicView(pid, cid, did) {
    console.log(pid, cid, did);
    var tid = "#"+pid+"--"+cid+"--"+did;
    var toggle = $(tid);
    var pane = $(tid+"-pane");
    var is_visible = pane.is(":visible");
    $("."+pid+"-subpane").hide();
    $("."+pid+"-tlink").removeClass("active");
    if (!is_visible) {
        pane.show();
        $(tid+"-filter-btn").addClass("active");
        // We need to trigger the change event multiple times since toggleTopic is written assuming the cycle -1 -> 0 -> 1 -> -1
        $(tid).attr('data-chosen', 0);
        if (toggle.val() == "-1") {
            $(tid).val(0)
            $(tid).trigger('change');
        } else if (toggle.val() == "1") {
            $(tid).val(-1)
            $(tid).trigger('change');
            $(tid).val(0)
            $(tid).trigger('change');
        }
    }
}

var filter_menus = ['topic', 'language'];
var filter_classes = [['.topic-filtered', topicFiltering], ['.language-filtered', languageFiltering], ['.calendar-filtered', calFiltering]];
function talksToShow(talks) {
    for (i=0; i<filter_classes.length; i++) {
        if (filter_classes[i][1]()) {
            talks = talks.not(filter_classes[i][0]);
            console.log("talksToShow", filter_classes[i][0], talks.length);
        }
    }
    return talks;
}
function filterMenuId(ftype) {
    if (ftype == "topic") {
        return "#root--topic--0-pane";
    } else {
        return "#"+ftype+"-filter-menu";
    }
}
function filterMenuVisible(ftype) {
    return $(filterMenuId(ftype)).is(":visible");
}
function toggleFilters(id, on_menu_open=false) {
    console.log("filters", id);
    if (id !== null) {
        console.log($('#'+id).val());
        var is_enabled = ($('#'+id).val() == 1);
        var ftype = id;
        setCookie("filter_" + ftype, is_enabled ? "1" : "0");
        if (!on_menu_open && is_enabled && !filterMenuVisible(ftype) && !getCookie(ftype+"s")) {
            toggleFilterView(ftype+"-filter-btn");
        }
    }
    var talks = $('.talk');
    talks.hide();
    talks = talksToShow(talks);
    talks.show();
    apply_striping();
}
function toggleFilterView(id) {
    // If this filter is not enabled, we enable it
    console.log("filterview", id);
    var ftype = id.split("-")[0];
    var is_enabled = (getCookie("filter_"+ftype) == "1");
    var visible = filterMenuVisible(ftype)
    console.log("enabled", is_enabled, "visible", visible);
    if (!is_enabled && !visible) {
        setToggle(ftype, 1);
        toggleFilters(ftype, true);
    }
    for (i=0; i<filter_menus.length; i++) {
        var menu = $(filterMenuId(filter_menus[i]));
        var link = $("#"+filter_menus[i]+"-filter-btn");
        if (ftype == filter_menus[i]) {
            menu.slideToggle(150);
            link.toggleClass("active");
        } else {
            menu.slideUp(150);
            link.removeClass("active");
        }
    }
}

function apply_striping() {
  $('#browse-talks tbody tr:visible:odd').css('background', '#E3F2FD');
  $('#browse-talks tbody tr:visible:even').css('background', 'none');
}

function tickClock() {
    var curtime = $("#curtime").text();
    var hourmin = curtime.split(":");
    hourmin[1] = parseInt(hourmin[1]) + 1;
    if (hourmin[1] == 60) {
        hourmin[1] = 0;
        hourmin[0] = parseInt(hourmin[0]) + 1;
        if (hourmin[0] == 24) hourmin[0] = 0;
        hourmin[0] = hourmin[0].toString();
    }
    hourmin[1] = hourmin[1].toString().padStart(2, '0');
    curtime = hourmin.join(":");
    $("#curtime").text(curtime);
}

var selectPureClassNames = {
    select: "select-pure__select",
    dropdownShown: "select-pure__select--opened",
    multiselect: "select-pure__select--multiple",
    label: "select-pure__label",
    placeholder: "select-pure__placeholder",
    dropdown: "select-pure__options",
    option: "select-pure__option",
    autocompleteInput: "select-pure__autocomplete",
    selectedLabel: "select-pure__selected-label",
    selectedOption: "select-pure__option--selected",
    placeholderHidden: "select-pure__placeholder--hidden",
    optionHidden: "select-pure__option--hidden",
};
function makeTopicSelector(topicOptions, initialTopics) {
    function callback_topics(value) {
        $('input[name="topics"]')[0].value = '[' + value + ']';
    }
    return new SelectPure("#topic_selector", {
        onChange: callback_topics,
        options: topicOptions,
        multiple: true,
        autocomplete: true,
        icon: "fa fa-times",
        inlineIcon: false,
        value: initialTopics,
        classNames: selectPureClassNames,
    });
}
function defaultLanguage() {
    var languages = getCookie("languages");
    if (!languages) {
        return "en";
    } else {
        languages = languages.split(",");
        if (languages.includes("en")) {
            return "en";
        } else {
            languages.sort();
            return languages[0];
        }
    }
}

function makeInstitutionSelector(instOptions, initialInstitutions) {
    function callback_institutions(value) {
        $('input[name="institutions"]')[0].value = '[' + value + ']';
    }
    return new SelectPure("#institution_selector", {
        onChange: callback_institutions,
        options: instOptions,
        multiple: true,
        autocomplete: true,
        icon: "fa fa-times",
        inlineIcon: false,
        value: initialInstitutions,
        classNames: selectPureClassNames,
    });
}
function makeLanguageSelector(langOptions, initialLanguage) {
    function callback_language(value) {
        $('input[name="language"]').value = value;
    }
    return new SelectPure("#language_selector", {
        onChange: callback_language,
        options: langOptions,
        autocomplete: true,
        value: initialLanguage,
        classNames: selectPureClassNames,
    });
}
function makeSubjectSelector(subjOptions, initialSubjects) {
    function callback_subjects(value) {
      // hidden inputs by default don't trigger a change event
        $('input[name="subjects"]').val('[' + value + ']').trigger('change');
    }
    return new SelectPure("#subject_selector", {
        onChange: callback_subjects,
        options: subjOptions,
        multiple: true,
        autocomplete: true,
        icon: "fa fa-times",
        inlineIcon: false,
        value: initialSubjects,
        classNames: selectPureClassNames,
    });
}

function copySourceOfId(id) {
  var copyText = $("#"+id);
  copyText.select();
  document.execCommand("copy");
  console.log("Copied!");
  copyText.notify("Copied!", {className: "success", position:"bottom right" });
}

function displayCookieBanner() {
    console.log("showing banner");
    $.notify.addStyle('banner', {
        html: "<div><div class='message' data-notify-html='message'/><div><button class='yes' data-notify-text='button'></button></div></div></div>",
    });

    //listen for click events from this style
    $(document).on('click', '.notifyjs-banner-base .yes', function() {
        //hide notification
        $(this).trigger('notify-hide');
        setCookie("cookie_banner", "nomore");
    });
    $.notify({
        message: 'This website uses cookies to improve your experience.',
        button: 'Got it!'
    }, {
        style: 'banner',
        position: 'b r',
        autoHide: false,
        clickToHide: false
    });
}

$(document).ready(function () {
    if (navigator.cookieEnabled && !document.cookie.includes('cookie_banner')) {
        displayCookieBanner();
    }

    if (navigator.cookieEnabled) {
        reviseCookies();
    }

    $('.toggler-nav').click(
        function (evt) {
            evt.preventDefault();
            toggle_time(this.id);
            return false;
        });
    $('.subject_toggle').click(
        function (evt) {
            evt.preventDefault();
            toggleSubject(this.id);
        });
    $('.language_toggle').click(
        function (evt) {
            evt.preventDefault();
            toggleLanguage(this.id);
        });

    var today = new Date();
    var minute = today.getMinutes();
    var millisecond = 1000 * today.getSeconds() + today.getMilliseconds();
    var displayed_minute = parseInt($("#curtime").text().split(":")[1]);
    // We might have passed a minute barrier between the server setting the time and the page finishing loading
    // Because of weird time zones (the user time preference may not be their local clock time),
    // we only do something if the minute is offset by 1 or 2 (for a super-slow page load)
    if (minute == displayed_minute + 1) {
        tickClock();
    } else if (minute == displayed_minute + 2) {
        tickClock(); tickClock();
    }
    setTimeout(function() {
        tickClock();
        // update the clock in the top right every 60 seconds
        setInterval(function() {
          tickClock();
        }, 60000);
    }, 60000 - millisecond);
});

$(document).ready(function() {
  dr = $("input[name='daterange']")
  var beginningoftime = 'January 1, 2020';
  var endoftime = 'January 1, 2050';
  var start = moment();
  var end = moment().add(6, 'days');
  if( dr.length > 0 ) {
    var drval = dr[0].value;
    if( drval.includes('-') ) {
      var se = drval.split('-');
      start = se[0].trim();
      end = se[1].trim();
    } else {
      start = beginningoftime;
      end = endoftime;
    }
    if(start == '') {
      start = beginningoftime;
    }
    if(end == '') {
      end = endoftime;
    }
  }


  function cd(start, end, label) {
      if(start.format('MMMM D, YYYY') == beginningoftime){
        start = '';
      } else {
        start = start.format('MMMM D, YYYY')
      }
      if(end.format('MMMM D, YYYY') == endoftime) {
        end = '';
      } else {
        end =  end.format('MMMM D, YYYY')
      }
      // everything is a string from now on
      if(start == "Invalid date") {
        start = ''
      }
      if(end == "Invalid date") {
        end = ''
      }
      if(start == '' && end == '') {
        $('#daterange').val('');
      } else {
        $('#daterange').val(start + ' - ' + end);
      }
    };


  $('input[name="daterange"]').on('cancel.daterangepicker', function(ev, picker) {
      $(this).val('');
  });

    $('#daterange').daterangepicker({
        startDate: start,
        endDate: end,
        autoUpdateInput: false,
        opens: "center",
        drops: "down",
        ranges: {
           'No restriction': [beginningoftime, endoftime],
           'Future': [moment(), endoftime],
           'Past': [beginningoftime, moment()],
           'Today': [moment(), moment()],
           'Next 7 Days': [moment(), moment().add(6, 'days')],
           'Next 30 Days': [moment(), moment().add(29, 'days')],
        },
        locale: {
          format: "MMMM D, YYYY",
        },
      },
      cd
    );

    //cb(start, end);


});



//handling subscriptions
$(document).ready(function(){
    $("input.subscribe").change(function(evt) {
        var elem = $(this);
        function success(msg) {
          // this is the row
          var row = elem[0].parentElement.parentElement;
          $(row).notify(msg, {className: "success", position:"right" });
          //evt.stopPropagation();
          var name = elem[0].name;
          // is a seminar
          if( ! name.includes('/') ){
            // apply the same thing to the talks of that seminar
            foo = $('input.subscribe[id^="tlg' + name +'--"]');
            $('input.subscribe[id^="tlg' + name +'--"]').val(elem.val());
            $('input.subscribe[id^="tlg' + name +'--"]').attr('data-chosen', elem.val());
          } else {
            // for the browse page
            if( elem.val() == "1" ) {
              $(row).removeClass("calendar-filtered");
            } else {
              $(row).addClass("calendar-filtered");
            }
          }
        }
        function error(xhr) {
          // this is the row
          var msg = xhr.responseText
          console.log(msg);
          $(elem[0].parentElement.parentElement).notify(msg, {className: "error", position:"right" });
          // revert
          evt.stopPropagation();
          elem.val(-parseInt(elem.val()));
          elem.attr('data-chosen', elem.val());
        }
        console.log($(this).val());
        if($(this).val() == "1") {
            $.ajax({
              url: '/user/subscribe/' +  $(this)[0].name,
              success: success,
              error: error
            });
              console.log('/user/subscribe/' +  $(this)[0].name);
        } else {
          $.ajax({
            url: '/user/unsubscribe/' +  $(this)[0].name,
            success: success,
            error: error
          });
            console.log('/user/unsubscribe/' +  $(this)[0].name);
        }
    });
});



function checkpw() {
  var match = "Too short";
  if($("#pw1").val().length < 8){
    "Too short (less than 8 characters)";
    $("#pw1status").html("Too short (less than 8 characters)");
    $("#pw2status").html("");
  } else {
    $("#pw1status").html("");
  }

  if($("#pw1").val() == $("#pw2").val()) {
    $("#pw2status").html("");
  } else {
    $("#pw2status").html("Not matching");
  }
}




/* jstree initialization */

function makeTree(json_tree) {
  function mark_undetermined_nodes(instance) {
    console.log("mark_undetermined_nodes");
    bar = instance;
    // remove class for every node
    $('a > i.jstree-checkbox').removeClass('jstree-undetermined')
    instance.get_bottom_checked(true).reduce(
      function (acc, node) {
        let union = new Set(acc)
        for (let elt of node.parents) {
          union.add(elt)
        }
        return union}, new Set()
    ).forEach(
      function(id) {
        if( id != '#' ) {
          $('#' + id + ' > a > i.jstree-checkbox').addClass('jstree-undetermined')
        }
      }
    )
  }

  $('#topicDAG').jstree({
    "checkbox" : {
      "three_state": false,
      "cascading": "",
    },
    "search": {
      "show_only_matches": true,
    },
    'core': {
      'data' : json_tree,
      'worker': false,
      'loaded_state': true,
      'themes': {
        'name': 'proton',
        "stripes" : true,
        "icons": false,
        "responsive": true,
      },
    },
    "plugins": ["checkbox", "wholerow", "search"]
  });
  // bind to events triggered on the tree
  $('#topicDAG').on("changed.jstree", function (e, data) {
    if( data.node !== undefined) {
      foo = data;
      //stop propagation
      e.preventDefault();
      var selected = data.instance.is_selected(data.node);
      var vertex = data.node.li_attr['vertex'];
      var vertices = data.instance.get_json('#', { flat: true }).reduce(
        function (acc, node) {
          if( node.li_attr['vertex'] == data.node.li_attr['vertex'] ) {
            return acc.concat([node.id]);
          } else {
            return acc;
          }
        }, []);
      if( selected ) {
        // select the parents of every vertex
        vertices.forEach(function(id) {
          var nodev = data.instance.get_node(id)
          data.instance.check_node(nodev);
          data.instance.check_node(nodev.parents);
        });
      } else {
        // reselect if any children are selected
        if ( data.instance.get_checked_descendants(data.node['id']).length > 0 ) {
          data.instance.check_node(data.node);
          data.instance.select_node(data.node);
        } else {
          // deselect other vertices
          vertices.forEach(function(id) {
            var nodev = data.instance.get_node(id)
            data.instance.uncheck_node(nodev);
          });
        }
      }
    }
    // figure out undetermined nodes
    if( data.instance !== undefined ) {
      mark_undetermined_nodes(data.instance);
    }
  });
  $('#topicDAG').on('open_node.jstree',
    function (e, data) {
      // figure out undetermined nodes
      if( data.instance !== undefined ) {
        mark_undetermined_nodes(data.instance);
      }
    }
  )

  $('#deselect_all').on('click', function () {
    $('#topicDAG').jstree('deselect_all');
  });

  var to = false;
  $('#topicDAG_search').keyup(function () {
    if(to) { clearTimeout(to); }
    to = setTimeout(function () {
      var v = $('#topicDAG_search').val();
      $('#topicDAG').jstree(true).search(v);
    }, 250);
  });
}
