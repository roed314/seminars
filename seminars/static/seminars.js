
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

$(document).ready(function () {
    $('#timetoggle').click(
        function (evt) {
            evt.preventDefault();
            toggle_time();
            return false;
        });
});

foo = moment();

$(document).ready(function() {

  var start = moment().subtract(29, 'days');
  var end = moment();
  var beginningoftime = '01/01/2020';



  $('input[name="daterange"]').on('cancel.daterangepicker', function(ev, picker) {
      $(this).val('');
  });

    $('#daterange').daterangepicker({
        startDate: start,
        endDate: end,
        autoUpdateInput: false,
        ranges: {
           'No restriction': ['', ''],
           'Future': [moment(), ''],
           'Past': [beginningoftime, moment()],
           'Today': [moment(), moment()],
           'Yesterday': [moment().subtract(1, 'days'), moment().subtract(1, 'days')],
           'Last 7 Days': [moment().subtract(6, 'days'), moment()],
           'Last 30 Days': [moment().subtract(29, 'days'), moment()],
           'This Month': [moment().startOf('month'), moment().endOf('month')],
           'Last Month': [moment().subtract(1, 'month').startOf('month'), moment().subtract(1, 'month').endOf('month')]
        },
      },
      function cb(start, end, label) {
      foo = start;
      console.log(start);
      console.log(end);
      if(start != '') {
        if(start.format('MM/DD/YYYY') == beginningoftime){
          start = '';
        } else {
          start = start.format('MMMM D, YYYY')
        }
      }
      if(end != '') {
        end =  end.format('MMMM D, YYYY')
      }
      if(start == "Invalid date") {
        start = ''
      }
      if(end == "Invalid date") {
        end = ''
      }
      $('input[name="daterange"]').val(start + ' - ' + end);
      console.log('New date range selected: ' + start + ' to ' + end +  " label = " + label + ')');
    }
    );

    //cb(start, end);


});


