
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
    document.cookie = name + "=" + (value || "") + ";path=/";
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

function topicFiltering() {
    return $('#enable_topic_filter').is(":checked");
}
function languageFiltering() {
    return $('#enable_language_filter').is(":checked");
}
function calFiltering() {
    return $('#enable_calendar_filter').is(":checked");
}

function setLanguageLinks() {
    var cur_languages = getCookie("languages");
    if (cur_languages == null) {
        setCookie("languages", "en");
        cur_languages = "en";
        setCookie("filter_language", "0");
    } else {
        $('#enable_language_filter').prop("checked", Boolean(parseInt(getCookie("filter_languages"))));
    }
    cur_languages = cur_languages.split(",");
    for (var i=0; i<cur_languages.length; i++) {
        $("#langlink-" + cur_languages[i]).addClass("languageselected");
        $(".lang-" + cur_languages[i]).removeClass("language-filtered");
    }
}
function setLinks() {
    setLanguageLinks();
    var cur_topics = getCookie("topics");
    $(".talk").addClass("topic-filtered");
    if (cur_topics == null) {
        setCookie("topics", "");
        setCookie("filter_topic", "0");
        // filter_language set in setLanguageLinks(), since we added it after launch
        setCookie("filter_calendar", "0");
        // Set the following in preparation so we don't need to worry about them not existing.
        setCookie("filter_location", "0");
        setCookie("filter_time", "0");
    } else {
        $('#enable_topic_filter').prop("checked", Boolean(parseInt(getCookie("filter_topic"))));
        $('#enable_language_filter').prop("checked", Boolean(parseInt(getCookie("filter_language"))));
        $('#enable_calendar_filter').prop("checked", Boolean(parseInt(getCookie("filter_calendar"))));
        cur_topics = cur_topics.split(",");
        for (var i=0; i<cur_topics.length; i++) {
            $("#topiclink-" + cur_topics[i]).addClass("topicselected");
            $(".topic-" + cur_topics[i]).removeClass("topic-filtered");
        }
        toggleFilters(null);
    }
}
function toggleLanguage(id) {
    var toggler = $("#" + id);
    console.log(id);
    var lang = id.substring(9); // langlink-*
    var talks = $(".lang-" + lang);
    if (toggler.hasClass("languageselected")) {
        toggler.removeClass("languageselected");
        cur_langs = removeFromCookie(lang, "languages").split(",");
        for (i=0; i<cur_langs.length; i++) {
            talks = talks.not(".lang-" + cur_langs[i]);
        }
        talks.addClass("language-filtered");
        if (languageFiltering()) {
            talks.hide();
            apply_striping();
        }
    } else {
        toggler.addClass("languageselected");
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
function toggleTopic(id) {
    var toggler = $("#" + id);
    console.log(id);
    var topic = id.substring(10); // topiclink-*
    var talks = $(".topic-" + topic);
    if (toggler.hasClass("topicselected")) {
        toggler.removeClass("topicselected");
        cur_topics = removeFromCookie(topic, "topics").split(",");
        for (i=0; i<cur_topics.length; i++) {
            talks = talks.not(".topic-" + cur_topics[i]);
        }
        talks.addClass("topic-filtered");
        if (topicFiltering()) {
            talks.hide();
            apply_striping();
        }
    } else {
        toggler.addClass("topicselected");
        addToCookie(topic, "topics");
        talks.removeClass("topic-filtered");
        if (topicFiltering()) {
            // elements may be filtered by other criteria
            talks = talksToShow(talks);
            talks.show();
            apply_striping();
        }
    }
}
function getAllTopics() {
    var toggles = []
    $(".topic_toggle").each(function() {
        toggles.push(this.id.substring(10));
    })
    return toggles;
}
function selectAllTopics() {
    var toggles = getAllTopics();
    setCookie("topics", toggles.join(","));
    $(".topic_toggle").addClass("topicselected");
    var talks = $(".talk");
    talks.removeClass("topic-filtered");
    if (topicFiltering()) {
        talks = talksToShow(talks);
        talks.show();
        apply_striping();
    }
}
function clearAllTopics() {
    setCookie("topics", "");
    var toggles = getAllTopics();
    $(".topic_toggle").removeClass("topicselected");
    var talks = $(".talk");
    talks.addClass("topic-filtered");
    if (topicFiltering()) {
        talks.hide();
        // no need to apply striping since no visible talks
    }
}

var filter_classes = [['.topic-filtered', topicFiltering], ['.language-filtered', languageFiltering], ['.calendar-filtered', calFiltering]]
function talksToShow(talks) {
    for (i=0; i<filter_classes.length; i++) {
        if (filter_classes[i][1]()) {
            talks = talks.not(filter_classes[i][0]);
            console.log(talks.length);
        }
    }
    return talks;
}
function toggleFilters(id) {
    console.log(id);
    if (id !== null) {
        console.log($('#'+id).is(":checked"));
        setCookie("filter_" + id.split("_")[1], $('#'+id).is(":checked") ? "1" : "0");
    }
    var talks = $('.talk');
    console.log(talks.length);
    talks.hide();
    talks = talksToShow(talks);
    talks.show();
    apply_striping();
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

$(document).ready(function () {

    setLinks();

    $('.toggler-nav').click(
        function (evt) {
            evt.preventDefault();
            toggle_time(this.id);
            return false;
        });
    $('.topic_toggle').click(
        function (evt) {
            evt.preventDefault();
            toggleTopic(this.id);
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
    $("input.subscribe:checkbox").change(function(evt) {
        var elem = $(this);
        function success(msg) {
          // this is the row
          var row = elem[0].parentElement.parentElement;
          $(row).notify(msg, {className: "success", position:"right" });
          //evt.stopPropagation();
          var value = elem[0].value;
          // is a seminar
          if( ! elem[0].value.includes('/') ){
            // apply the same thing to the talks of that seminar
            console.log('input.subscribe[id^="tlg' + value +'/"]');
            console.log(elem.is(":checked"));
            $('input.subscribe[id^="tlg' + value +'/"]').prop("checked", elem.is(":checked"));
          } else {
            // for the browse page
            if( elem.is(":checked") ) {
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
          elem.prop("checked", ! elem.is(":checked"));
        }
        if($(this).is(":checked")) {
            $.ajax({
              url: '/user/subscribe/' +  $(this)[0].value,
              success: success,
              error: error
            });
              console.log('/user/subscribe/' +  $(this)[0].value);
        } else {
          $.ajax({
            url: '/user/unsubscribe/' +  $(this)[0].value,
            success: success,
            error: error
          });
            console.log('/user/unsubscribe/' +  $(this)[0].value);
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


