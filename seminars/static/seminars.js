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
  if( topic != "" ) {
    var cookie = getCookie("topics_dict");
    if (cookie == null || cookie == "") {
        var cur_items = [];
    } else {
        var cur_items = cookie.split(",").filter(elt => ! elt.startsWith(":"));
    }
    var new_item = topic + ":" + value.toString();
    var found = false;
    for (let i=0; i < cur_items.length; i++) {
        if (cur_items[i].startsWith(topic + ":")) {
            cur_items[i] = new_item
            found = true;
            break;
        }
    }
    if (!found) {
        cur_items.push(new_item);
    }
    console.log("cur_items", cur_items);
    setCookie("topics_dict", cur_items.join(","));
  }
}
function getTopicCookie(topic) {
    var cur_items = getCookie("topics_dict").split(",");
    for (let i=0; i < cur_items.length; i++) {
        if (cur_items[i].startsWith(topic + ":")) {
            return parseInt(cur_items[i].substring(topic.length+1));
        }
    }
    return 0;
}
/*
function getTopicCookieWithValue(value) {
    value = value.toString();
    var cur_items = getCookie("topics_dict").split(",").filter(elt => ! elt.startsWith(":"));
    console.log("cur_items", cur_items);
    var with_value = [];
    for (var i=0; i<cur_items.length; i++) {
        if (cur_items[i].endsWith(":" + value)) {
            with_value.push(cur_items[i].split(':')[0]);
        }
    }
    return with_value;
}
*/
function _val(id) {
    var toggle = $('#'+id);
    return parseInt(toggle.attr('data-chosen'));
}
function setToggle(id, value, trigger=false) {
    var toggle = $('#'+id);
    toggle.val(value)
    toggle.attr('data-chosen', value);
    if (trigger) {
        toggle.trigger('change');
    }
}
function setOtherToggles(tid, value) {
    var toggles = $(".tgl." + tid);
    toggles.val(value);
    toggles.attr('data-chosen', value);
}

function topicFiltering() {
    return _val('topic') == 1;
}
function enableTopicFiltering() {
    setCookie("filter_topic", "1");
    setToggle("topic", 1);
    toggleFilters(null);
}
function languageFiltering() {
    return _val('language') == 1;
}
function enableLanguageFiltering() {
    setCookie("filter_language", "1");
    setToggle("language", 1);
    toggleFilters(null);
}
function calFiltering() {
    return _val('calendar') == 1;
}
function moreFiltering() {
    return _val('more') == 1;
}
function enableMoreFiltering() {
    setCookie("filter_more", "1");
    setToggle("more", 1);
    toggleFilters(null);
}

function topicFromTriple(tripleid) {
    return tripleid.split("--")[1];
}

function reviseCookies() {
    // This function sets cookies initially if they aren't set and changes them when needed by code changes
    if (getCookie("languages") == null) {
        setCookie("languages", "");
    }
    if (getCookie("mores") == null) {
        setCookie("mores", "");
    }
    if (getCookie("topics_dict") == null) {
        cur_topics = getCookie("topics");
        if (cur_topics == null || cur_topics == "") {
            setCookie("topics_dict", "");
        } else {
            cur_topics = cur_topics.split(",");
            cur_subjects = getCookie("subjects");
            if (cur_subjects == null) {
                cur_subjects = "";
            } else {
                cur_subjects = cur_subjects.split(",");
            }
            cur_topics = cur_subjects.concat(cur_topics).filter(elt => elt != "");
            cur_topics = cur_topics.map( function(top) { return top + ":1" });
            setCookie("topics_dict", cur_topics.join(","));
            eraseCookie("topics");
        }
    }
    var ftypes = ["topic", "language", "calendar", "more", "time", "location"];
    var pm1 = ["-1", "1"];
    for (i=0; i<ftypes.length; i++) {
        if (!(getCookie("filter_"+ftypes[i]) in pm1)) {
            setCookie("filter_"+ftypes[i], "-1");
        }
    }
}

function enableMoreButton() {
    $('#more-filter-menu button').html("Apply");
    $('#more-filter-menu button').prop('disabled', false);
}
function disableMoreButton() {
    $('#more-filter-menu button').html("Applied");
    $('#more-filter-menu button').prop('disabled', true);
}
function moreHasChanges() {
    return $("#more-filter-menu input,#more-filter-menu select").filter(function() {
        return $(this).val() != getCookie("search_" + this.name)
    }).length != 0
}
function setMoreButton() {
    // This function can be called when the more input fields are changed or the more toggle changes to correctly set the state of the Apply/Applied button
    if (!moreFiltering() || moreHasChanges()) {
        enableMoreButton();
    } else {
        disableMoreButton();
    }
}
function setSearchCookies() {
    $("#more-filter-menu input,#more-filter-menu select").each(function() {
        console.log("SearchCookie", this.name, $(this).val());
        setCookie("search_" + this.name, $(this).val());
    });
    setCookie("filter_more", "1");
}
function reloadForCookies() {
    setSearchCookies();
    window.location.reload(true);
}
function pushForCookies() {
    if (moreHasChanges()) {
        reloadForCookies();
    } else {
        if (!moreFiltering()) {
            setToggle("more", 1);
            toggleFilters("more", true);
        }
        disableMoreButton();
    }
}

function toggleLanguage_core(id) {
    var toggleval = _val(id);
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

function toggleLanguage(togid) {
  console.log(togid);
  var foo = togid;
  setTimeout(() => toggleLanguage_core(foo), 1);
}


function toggleTopicDAG_core(togid) {
    var previous = $('input.sub_topic:not(.disabled)[data-chosen="1"]').toArray().map( elt => $(elt).attr("name") );
    var topic = topicFromTriple(togid);
    var toggleval = _val(togid);
    setTopicCookie(topic, toggleval);
    // Update other toggles in other parts of the tree that have the same id
    setOtherToggles(topic, toggleval);
    if (toggleval == 0) {
        $("#" + togid + "-pane " + "input.tgl.sub_" + topic).removeClass("disabled");
        $("#" + togid + "-pane " + "a.sub_"+topic + ", " + "#" + togid + "-pane " + "span.sub_"+topic).removeClass("not_toggleable");
        var pane = $("#"+togid+"-pane");
        var is_visible = pane.is(":visible");
        if (!is_visible) {
            var triple = togid.split("--");
            toggleTopicView(triple[0], triple[1], triple[2]);
        }
      /*
        // Need to show rows corresponding to sub-topics.
        // We can't just use $("tgl.sub_"+topic).each(),
        // since some 1s may be under -1s.
        var blocking_toggles = [];
        $('input[data-chosen="-1"].tgl3way.sub_'+topic).each(function() {
            blocking_toggles.push(topicFromTriple(this.id));
        });
        console.log("blocking_toggles", blocking_toggles);
        var show_selector = $('input[data-chosen="1"].sub_'+topic);
        for (let i=0; i<blocking_toggles.length; i++) {
            show_selector = show_selector.not(".sub_"+blocking_toggles[i]);
        }
        show_selector.each(function() {
            to_show.push(topicFromTriple(this.id));
        });
        */
    } else {
        console.log("togid = ", togid);
        $("#" + togid + "-pane input.tgl").addClass("disabled");
        if (toggleval == 1) {
        //    to_show.push(topic);
          previous = previous.filter(item => item !== topic)
        } else {
            $("#" + togid + "-pane " + "a.sub_" + topic + ", " + "#" + togid + "-pane " + "span.sub_"+topic).addClass("not_toggleable");
            previous = previous.concat([topic]);
        //   to_hide.push(topic);
        }
        previous = Array.from(new Set(previous));
    }
    var now = Array.from( new Set($('input.sub_topic:not(.disabled)[data-chosen="1"]').toArray().map( elt => $(elt).attr("name") )));
    var to_hide = previous.filter(x => !now.includes(x) );
    // We cannot take the difference to figure out to_show
    // if previous = [math, math-ph], and now = [math-ph],
    // if we take the difference then to_show = []
    var to_show = now; //  now.filter(x => !previous.includes(x) );
    console.log("now ", now);
    console.log("previous ", previous);
    console.log("to_show ", to_show);
    console.log("to_hide ", to_hide);
    if (to_hide.length > 0) {
        var talks = $();
        for (let i=0; i < to_hide.length; i++) {
            talks = talks.add(".talk.topic-" + to_hide[i]);
        }
        var cur_topics = to_show; //getTopicCookieWithValue(1);
        for (let i=0; i<cur_topics.length; i++) {
            talks = talks.not(".topic-" + cur_topics[i]);
        }
        talks.addClass("topic-filtered");
        if (topicFiltering()) {
            talks.hide();
        }
    }
    if (to_show.length > 0) {
        var talks = $();
        for (let i=0; i < to_show.length; i++) {
            talks = talks.add(".talk.topic-filtered.topic-" + to_show[i]);
        }
        talks.removeClass("topic-filtered");
        if (topicFiltering()) {
            // elements may be filtered by other criteria
            talks = talksToShow(talks);
            talks.show();
        }
    }
    if (topicFiltering() && (to_show.length  + to_show.length) > 0) {
      apply_striping();
    }

}

function toggleTopicDAG(togid) {
  console.log(togid);
  var foo = togid;
  setTimeout(() => toggleTopicDAG_core(foo), 1);
}

function anyHasValue(selector, value) {
    return $(selector).filter(function() { return _val(this.id) == value; }).length > 0;
}

function toggleTopicView(pid, cid, did) {
  console.log(pid, cid, did);
  var tid = pid+"--"+cid+"--"+did;
  var pane = $("#"+tid+"-pane");
  var is_visible = pane.is(":visible");
  $("."+pid+"-subpane:visible").each(function () {
    lastid = this.id.substring(0, this.id.length - 5); // remove -pane
    lastcid = lastid.split("--")[1];
    if (_val(lastid) == 0 && !anyHasValue(".tgl.sub_" + lastcid, 1)) {
      setToggle(lastid, 1, trigger=true);
      setToggle(lastid, -1, trigger=true);
    }
    $(this).hide();
  });
  $("."+pid+"-tlink").removeClass("active");
  if (is_visible) {
    if (_val(tid) == 0 && !anyHasValue(".tgl.sub_" + cid, 1)) {
      setToggle(tid, 1, trigger=true);
      setToggle(tid, -1, trigger=true);
    }
  } else {
    pane.show();
    $("#"+tid+"-filter-btn").addClass("active");
    if ( !$("#"+tid).hasClass("disabled") ) {
      // We need to trigger the change event multiple times since toggleTopic is written assuming the cycle -1 -> 0 -> 1 -> -1
      if (_val(tid) == -1) {
        setToggle(tid, 0, trigger=true);
      } else if (_val(tid) == 1) {
        console.log("\n\n\nhere");
        setToggle(tid, -1, trigger=true);
        setTimeout(() => setToggle(tid, 0, trigger=true), 2);
      }
    }
  }
}

var filter_menus = ['topic', 'language', 'more'];
var filter_classes = [['.topic-filtered', topicFiltering], ['.language-filtered', languageFiltering], ['.calendar-filtered', calFiltering], ['.more-filtered', moreFiltering]];
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
function toggleFilters_core(id, on_menu_open=false) {
    console.log("filters", id);
    if (id !== null) {
        var is_enabled = (_val(id) == 1);
        var ftype = id;
        setCookie("filter_" + ftype, is_enabled ? "1" : "-1");
        if (!on_menu_open && is_enabled && !filterMenuVisible(ftype) && !getCookie(ftype+"s")) {
            toggleFilterView(ftype+"-filter-btn");
        }
        if (ftype == "more") {
            if (is_enabled && moreHasChanges()) {
                return reloadForCookies();
            }
            if (is_enabled) {
                disableMoreButton();
            } else {
                enableMoreButton();
            }
        }
    }
    var talks = $('.talk');
    talks.hide();
    talks = talksToShow(talks);
    talks.show();
    apply_striping();
}
function toggleFilters(id, on_menu_open=false) {
  var copy_id = id;
  var copy_on_menu_open = on_menu_open;
  setTimeout( () => toggleFilters_core(copy_id, copy_on_menu_open), 1);
}

function shouldUnsetFilterToggle(ftype) {
    return (ftype == "more" &&
            $("#more-filter-menu input,#more-filter-menu select").filter(function () {
                return $.trim($(this).val()).length != 0
            }).length == 0 ||
            ftype != "more" &&
            !anyHasValue(".tgl.sub_" + ftype, "1"));
}
function toggleFilterView(id) {
    // If this filter is not enabled, we enable it
    console.log("filterview", id);
    var ftype = id.split("-")[0];
    console.log("ftype", ftype);
    var is_enabled = (getCookie("filter_"+ftype) == "1");
    var visible = filterMenuVisible(ftype)
    console.log("enabled", is_enabled, "visible", visible);
    if (!is_enabled && !visible) { // showing
        console.log("showing");
        if (ftype == "more") {
            setMoreButton();
        } else {
            setToggle(ftype, 1);
            toggleFilters(ftype, true);
        }
    } else if (visible) { // hiding
        console.log("hiding");
        if (shouldUnsetFilterToggle(ftype)) {
            setToggle(ftype, -1);
            toggleFilters(ftype, true);
        }
    }
    for (i=0; i<filter_menus.length; i++) {
        var menu = $(filterMenuId(filter_menus[i]));
        var link = $("#"+filter_menus[i]+"-filter-btn");
        if (ftype == filter_menus[i]) {
            setCookie("visible_" + filter_menus[i], visible ? "-1" : "1");
            menu.slideToggle(150);
            link.toggleClass("active");
        } else if (menu.is(":visible")) {
            setCookie("visible_" + filter_menus[i], "-1");
            if (shouldUnsetFilterToggle(filter_menus[i])) {
                setToggle(filter_menus[i], 1, trigger=true);
                setToggle(filter_menus[i], -1, trigger=true);
            }
            menu.slideUp(150);
            link.removeClass("active");
        }
    }
}

function apply_striping() {
    $('#browse-talks tbody tr:visible:odd').removeClass("evenrow").addClass("oddrow"); //.css('background', '#E3F2FD');
    $('#browse-talks tbody tr:visible:even').removeClass("oddrow").addClass("evenrow"); //css('background', 'none');
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
        $('input[name="language"]')[0].value = value;
    }
    return new SelectPure("#language_selector", {
        onChange: callback_language,
        options: langOptions,
        autocomplete: true,
        value: initialLanguage,
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
    $('.language_toggle').click(
        function (evt) {
            evt.preventDefault();
            toggleLanguage(this.id);
        });
    $('input[name="keywords"]').on(
        "input",
        function (e) {
            $(".search").removeClass("inactive");
            $(".cancel-search").removeClass("inactive");
        });
    $('button.cancel-search').on(
        "click",
        function (e) {
            $("input[name=keywords]").val("");
        });
    $('#more-filter-menu input,#more-filter-menu select').on(
        "input change",
        function (e) {
            setMoreButton();
        });
    // this is now done on the server side
    //for (let i=0; i<filter_menus.length; i++) {
    //    if (getCookie("visible_" + filter_menus[i]) == "1") {
    //        toggleFilterView(filter_menus[i]);
    //    }
    //}

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
  dr = $('#daterange')
  var past = $('input[name="past"]').val() === "True";
  var minDate = 'January 1, 2020';
  var maxDate = 'January 1, 2050';
  if (past) {
    maxDate = moment();
    dr.attr('placeholder', moment().format('- MMMM D, YYYY'));
  } else {
    minDate = moment();
  }

  var start = false;
  var end = false;
  function deduce_start_end_from_value() {
    var drval = dr.val();
    if( drval.includes('-') ) {
      var se = drval.split('-');
      start = se[0].trim();
      end = se[1].trim();
    }
    if(start == '') {
      start = false;
    }
    if(end == '') {
      end = false;
    }
  }
  if(dr.lenght > 0) {
    deduce_start_end_from_value();
  }

  console.log(start, end);
  var ranges = {
           //'No restriction': [minDate, maxDate],
           'Future': [moment(), maxDate],
           'Past': [minDate, moment()],
           'Today': [moment(), moment()],
           'Next 7 Days': [moment(), moment().add(6, 'days')],
           'Past 7 Days': [moment().subtract(6, 'days'), moment()],
           'Next 30 Days': [moment(), moment().add(29, 'days')],
           'Past 30 Days': [moment().subtract(29, 'days'), moment()],
        }
  if ( past ) {
    delete ranges['Future'];
    delete ranges['Next 7 Days'];
    delete ranges['Next 30 Days'];
  } else {
    delete ranges['Past'];
    delete ranges['Past 7 Days'];
    delete ranges['Past 30 Days'];
  }



  function cd(start, end, label) {
    console.log('cd');
      if(start.format('MMMM D, YYYY') == minDate && past){
        start = '';
      } else {
        start = start.format('MMMM D, YYYY')
      }
      if(end.format('MMMM D, YYYY') == maxDate && !past) {
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
        dr.val('');
      } else {
        dr.val(start + ' - ' + end);
      }
    };


  dr.on('cancel.daterangepicker', function(ev, picker) {
      $(this).val('');
  });


  dr.daterangepicker({
    startDate: start,
    endDate: end,
    minDate: minDate,
    maxDate: maxDate,
    autoUpdateInput: false,
    opens: "center",
    drops: "down",
    ranges: ranges,
    cancelButtonClasses: "cancelcolors",
    locale: {
      format: "MMMM D, YYYY",
    },
  },
    cd
  );

  var daterangepicker_changed = true; // the picker doesn't detect all changes
  dr.on('apply.daterangepicker', function(ev, picker) {
    if( daterangepicker_changed ) {
      cd(picker.startDate, picker.endDate, "");
    }
    daterangepicker_changed = false;
  });
  dr.on("keyup", function() {
    daterangepicker_changed = true;
  });

  // change the word Apply to Select
  dr.on("showCalendar.daterangepicker", function () {
    console.log($("div.daterangepicker button.applyBtn"));
    $("div.daterangepicker button.applyBtn").text("Select")
    $("div.daterangepicker button.cancelBtn").before($("div.daterangepicker button.applyBtn"));
  })




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
  var len = $("#pw1").val().length;
  $("#pw2status").html("");
  if (len == 0) { $("#pw1status").html("Don't use a password that you use elsewhere!"); $("#pw1status").css('color','black'); }
  if (len > 0 && len < 8) { $("#pw1status").html("Too short (less than 8 characters)"); $("#pw1status").css('color','red'); }
  if (len >= 8 ) {
    $("#pw1status").html("");
    if ($("#pw1").val() != $("#pw2").val()) { $("#pw2status").html("Not matching");  $("#pw2status").css('color','red'); }
  }
}

function uniqByKeepLast(a, key) {
    return [
        ...new Map(
            a.map(x => [key(x), x])
        ).values()
    ]
}


/* jstree initialization */

function makeTopicsTree(json_tree) {
  $("div.topicDAG").css("display", "none");
  $("div.topicDAG").html(
  `<input id="topicDAG_search" type="text", value="" placeholder="Search">
   <button class="cancel" id="topicDAG_deselect_all">Deselect all</button>
   <button class="cancel" id="topicDAG_close_all">Close all</button>
   <div id="topicDAG"></div>`);
  function mark_undetermined_nodes(instance) {
    console.log("mark_undetermined_nodes");
    bar = instance;
    // remove class from every node
    $('a > i.jstree-checkbox').removeClass('jstree-undetermined')
    instance.get_checked(true).reduce(
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




  function callback_topics(instance) {
    function cmp(a, b) {
      var ad = instance.get_checked_descendants(a.id).length > 0;
      var bd = instance.get_checked_descendants(b.id).length > 0;
      if( ad == bd) {
        //use depth
        return b.parents.length - a.parents.length;
      } else {
        if ( ad ) {
          return 1;
        } else {
          return -1;
        }
      }
    }
    var vertices = instance.get_selected(true).sort(cmp);
    var uniq_vertices = uniqByKeepLast(vertices, node => node.li_attr['vertex']).sort(cmp);
    $('input[name="topics"]')[0].value = "[" +
      uniq_vertices.reduce(
        function (acc, node) {
          return acc.concat(["'" + node.li_attr['vertex'] + "'"]);
        },
        []
      ).sort().join(', ') + "]";
    $('#topicDAG_selector').html(
      uniq_vertices.reduce(
        function (acc, node) {
          if(instance.get_checked_descendants(node.id).length == 0) {
            return acc.concat(["<span class='topic_label'>" + node.text + "<i class='fa fa-times' nodeid='" + node.id + "'></i ></span>"]);
          } else {
            return acc.concat(["<span class='topic_label'>" + node.text + "</span>"]);
          }
        },
        []
      ).join("\n")
    )
    $("span.topic_label > i[nodeid]").on('mouseup',
      function (e) {
        console.log("yellow");
        e.preventDefault();
        $.jstree.reference('#topicDAG').deselect_node($(this).attr('nodeid'));
      });
  }

  $('#topicDAG').jstree({
    "checkbox" : {
      "three_state": false,
      "cascading": "",
    },
    "search": {
      "show_only_matches": true, // show only nodes that match
      "show_only_matches_children": true, // still show their children
    },
    'core': {
      'data' : json_tree,
      'worker': false,
      'loaded_state': true,
      'themes': {
        'name': 'proton',
        "icons": false,
        "responsive": true,
      },
    },
    "plugins": ["checkbox", "wholerow", "search"]
  });
  // bind to events triggered on the tree
  $('#topicDAG').on("changed.jstree", function (e, data) {
    if( data.node !== undefined) {
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
          data.instance.select_node(nodev);
          data.instance.check_node(nodev.parents);
          data.instance.select_node(nodev.parents);
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
            data.instance.deselect_node(nodev);
          });
        }
      }
    }
    if( data.instance !== undefined ) {
      // figure out undetermined nodes
      mark_undetermined_nodes(data.instance);
      // add topics to hidden input and the desired box
      callback_topics(data.instance);
    }
  });
  $('#topicDAG').on('redraw.jstree',
    function (e, data) {
      // figure out undetermined nodes
      if( data.instance !== undefined ) {
        mark_undetermined_nodes(data.instance);
      }
    }
  )


  $('#topicDAG_deselect_all').on('click', function () {
    $('#topicDAG').jstree('deselect_all');
    return false;
  });
  $('#topicDAG_close_all').on('click', function () {
    $('#topicDAG').jstree('close_all');
    $('#topicDAG_search').val('');
    $('#topicDAG_search').trigger('keyup');
    return false;
  });

  var to = false;
  $('#topicDAG_search').keyup(function () {
    if(to) { clearTimeout(to); }
    to = setTimeout(function () {
      if( $('#topicDAG_search').val().length != 1 ) {
        var v = $('#topicDAG_search').val();
      } else {
        var v = '';
      }
      $('#topicDAG').jstree(true).search(v);
    }, 250);
  });

  $(document).mouseup(function(e)
    {
      var divcontainer = $("div.topicDAG");
      var spancontainer = $("span.topicDAG");
      if( e.target.matches("i[nodeid]") ) {
        divcontainer.show();
      } else if ( spancontainer.is(e.target) || spancontainer.has(e.target).length > 0) {
        divcontainer.toggle();
        if( divcontainer.css('display') != 'none' ){
          $('#topicDAG_search').focus();
        }
      } else if (!divcontainer.is(e.target) && divcontainer.has(e.target).length === 0) {
        divcontainer.hide();
      }
    });

}
