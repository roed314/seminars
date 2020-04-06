
function toggle_time() {
    var future = $('#future_talks');
    var past = $('#past_talks');
    if (future.is(":visible"))
    {
        future.hide();
        past.show();
    } else {
        past.hide();
        future.show();
    }
}

function toggle_filter() {
    var filt_btn = $('#filter-btn');
    var filt_menu = $("#filter-menu");
    filt_btn.text("Filter");
    if (filt_menu.is(":hidden")) {
        filt_menu.slideToggle(400, function() {filt_btn.text("Filter ∧")});
    } else {
        filt_menu.slideToggle(400, function() {filt_btn.text("Filter ∨")});
    }
    return false;
}

function setCookie(name,value) {
    document.cookie = name + "=" + (value || "") + ";path=/";
}
function getCookie(name) {
    var nameEQ = name + "=";
    var ca = document.cookie.split(';');
    for(var i=0;i < ca.length;i++) {
        var c = ca[i];
        while (c.charAt(0)==' ') c = c.substring(1,c.length);
        if (c.indexOf(nameEQ) == 0) return c.substring(nameEQ.length,c.length);
    }
    return null;
}
function eraseCookie(name) {
    document.cookie = name+'=; Max-Age=-99999999;';
}
const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
setCookie("browser_timezone", tz);
function addCategory(cat) {
    var cur_cats = getCookie("categories");
    if (cur_cats) {
        cur_cats = cur_cats + "," + cat;
    } else {
        cur_cats = cat;
    }
    setCookie("categories", cur_cats);
    return cur_cats;
}
function removeCategory(cat) {
    var cur_cats = getCookie("categories");
    cur_cats = cur_cats.replace(cat, "").replace(",,",",");
    if (cur_cats.startsWith(",")) cur_cats = cur_cats.slice(1);
    if (cur_cats.endsWith(",")) cur_cats = cur_cats.slice(0, -1);
    setCookie("categories", cur_cats);
    return cur_cats;
}

function setCategoryLinks() {
    var cur_cats = getCookie("categories")
    if (cur_cats == null) {
        cur_cats = "ALL";
        setCookie("categories", "ALL");
        $(".cat-all").removeClass("catunselected");
    }
    cur_cats = cur_cats.split(",");
    for (var i=0; i<cur_cats.length; i++) {
        $("#catlink-" + cur_cats[i]).addClass("catselected");
        $(".cat-" + cur_cats[i]).removeClass("catunselected");
    }
}
function toggleCategory(id) {
    var toggler = $("#" + id);
    var cat = id.substring(8);
    if (toggler.hasClass("catselected")) {
        toggler.removeClass("catselected");
        cur_cats = removeCategory(cat);
        // Have to handle ALL specially, since we need to add the other categories back in
        if (!cur_cats.includes("ALL")) $(".cat-" + cat).addClass("catunselected");
        if (cat == "ALL") setCategoryLinks();
    } else {
        toggler.addClass("catselected");
        addCategory(cat);
        $(".cat-" + cat).removeClass("catunselected");
    }
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

$(document).ready(function () {

    setCategoryLinks();

    $('#timetoggle').click(
        function (evt) {
            evt.preventDefault();
            toggle_time();
            return false;
        });
    $('.category_toggle').click(
        function (evt) {
            evt.preventDefault();
            toggleCategory(this.id);
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
        setInterval(function() {
            // update the clock in the top right every 60 seconds
        }, 60000);
    }, 60000 - millisecond);
});

$(document).ready(function() {

  var start = moment();
  var end = moment().add(6, 'days');
  var beginningoftime = '01/01/2020';
  var endoftime = '01/01/2050';



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
      },
      function(start, end, label) {
      if(start.format('MM/DD/YYYY') == beginningoftime){
        start = '';
      } else {
        start = start.format('MMMM D, YYYY')
      }
      if(end.format('MM/DD/YYYY') == endoftime) {
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
    }
    );

    //cb(start, end);


});



