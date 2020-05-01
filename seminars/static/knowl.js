/*
 * let slideUp = (target, duration=500) => {
    target.style.transitionProperty = 'height, margin, padding'
    target.style.transitionDuration = duration + 'ms'
    target.style.boxSizing = 'border-box'
    target.style.height = target.offsetHeight + 'px'
    target.offsetHeight
    target.style.overflow = 'hidden'
    target.style.height = 0
    target.style.paddingTop = 0
    target.style.paddingBottom = 0
    target.style.marginTop = 0
    target.style.marginBottom = 0
    window.setTimeout( () => {
      target.style.display = 'none'
      target.style.removeProperty('height')
      target.style.removeProperty('padding-top')
      target.style.removeProperty('padding-bottom')
      target.style.removeProperty('margin-top')
      target.style.removeProperty('margin-bottom')
      target.style.removeProperty('overflow')
      target.style.removeProperty('transition-duration')
      target.style.removeProperty('transition-property')
      //alert("!")
    }, duration)
  }

  let slideDown = (target, duration=500) => {
    target.style.removeProperty('display')
    let display = window.getComputedStyle(target).display

    if (display === 'none')
      display = 'block'

    target.style.display = display
    let height = target.offsetHeight
    target.style.overflow = 'hidden'
    target.style.height = 0
    target.style.paddingTop = 0
    target.style.paddingBottom = 0
    target.style.marginTop = 0
    target.style.marginBottom = 0
    target.offsetHeight
    target.style.boxSizing = 'border-box'
    target.style.transitionProperty = "height, margin, padding"
    target.style.transitionDuration = duration + 'ms'
    target.style.height = height + 'px'
    target.style.removeProperty('padding-top')
    target.style.removeProperty('padding-bottom')
    target.style.removeProperty('margin-top')
    target.style.removeProperty('margin-bottom')
    window.setTimeout( () => {
      target.style.removeProperty('height')
      target.style.removeProperty('overflow')
      target.style.removeProperty('transition-duration')
      target.style.removeProperty('transition-property')
    }, duration)
  }
  var slideToggle = (target, duration = 500) => {
    if (window.getComputedStyle(target).display === 'none') {
      return slideDown(target, duration)
    } else {
      return slideUp(target, duration)
    }
    */

/**
 * https://github.com/component/debounce
 * Returns a function, that, as long as it continues to be invoked, will not
 * be triggered. The function will be called after it stops being called for
 * N milliseconds. If `immediate` is passed, trigger the function on the
 * leading edge, instead of the trailing. The function also has a property 'clear' 
 * that is a function which will clear the timer to prevent previously scheduled executions. 
 *
 * Copyright (c) 2009-2018 Jeremy Ashkenas, DocumentCloud and Investigative
 * Reporters & Editors
 *
 * Permission is hereby granted, free of charge, to any person
 * obtaining a copy of this software and associated documentation
 * files (the "Software"), to deal in the Software without
 * restriction, including without limitation the rights to use,
 * copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the
 * Software is furnished to do so, subject to the following
 * conditions:
 *
 * The above copyright notice and this permission notice shall be
 * included in all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
 * EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES
 * OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
 * NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT
 * HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY,
 * WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
 * FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR
 * OTHER DEALINGS IN THE SOFTWARE.
 */
function debounce(func, wait, immediate){
	var timeout, args, context, timestamp, result
	if (null == wait) wait = 100

	function later() {
		var last = Date.now() - timestamp

		if (last < wait && last >= 0) {
			timeout = setTimeout(later, wait - last)
		} else {
			timeout = null
			if (!immediate) {
				result = func.apply(context, args)
				context = args = null
			}
		}
	}

	var debounced = function(){
		context = this
		args = arguments
		timestamp = Date.now()
		var callNow = immediate && !timeout
		if (!timeout) timeout = setTimeout(later, wait)
		if (callNow) {
			result = func.apply(context, args)
			context = args = null
		}

		return result
	}

	debounced.clear = function() {
		if (timeout) {
			clearTimeout(timeout)
			timeout = null
		}
	}

	debounced.flush = function() {
		if (timeout) {
			result = func.apply(context, args)
			context = args = null

			clearTimeout(timeout)
			timeout = null
		}
	}

	return debounced
}


  function defer(method, property) {
    if (window.hasOwnProperty(property)) {
      method();
    } else {
      console.log("waiting for " + property + "to be loaded")
      setTimeout(function() { defer(method, property) }, 100)
    }
  }



function knowl_click_handler(evt) {
  var knowl = evt.target || evt.srcElement
  var uid = knowl.getAttribute("knowl-uid")
  var output_id = 'knowl-output-' + uid
  var output = document.getElementById(output_id)
  var kwargs = knowl.getAttribute("kwargs")
  var tagname = knowl.parentNode.tagName.toLowerCase()

  var table_mode = tagname == "td" || tagname == "th"

  // if we already have the content, toggle visibility
  if (output) {
    if (table_mode) {
      output_id.parent().parent().slideToggle("fast")
    }
    output_id.slideToggle("fast")
    knowl.classList.toggle("active")
  } else {
    knowl.classList.add("active")
    // create the element for the content, insert it after the one where the
    // knowl element is included (e.g. inside a <h1> tag) (sibling in DOM)
    knowl_output = document.createElement('div')
    knowl_output.classList.add('knowl-output')
    knowl_output.setAttribute('id', output_id)
    knowl_output.innerHTML = '<div class="knowl"><div><div class="knowl-content">' + kwargs + '</div></div></div>'
    // behave a bit differently, if the knowl is inside a td or th in a table.
    // otherwise assume its sitting inside a <div> or <p>
    if(table_mode) {
      // assume we are in a td or th tag, go 2 levels up
      var td_tag = knowl.parentNode
      var tr_tag = td_tag.parentNode
      // create two rows

      // For alternating color tables
      var hiddenrow = document.createElement('tr')
      hiddenrow.className = tr_tag.className
      hiddenrow.classList.add('hidden')
      tr_tag.insertAdjacentElement('afterend', hiddenrow)

      // the real row
      var newrow = document.createElement('tr')
      newrow.className = tr_tag.className
      var col = document.createElement('td')
      col.setAttribute('colspan', 0)
      col.appendChild(knowl_output)
      newrow.appendChild(col)
      tr_tag.insertAdjacentElement('afterend', newrow)
    } else {
      knowl.parentNode.insertAdjacentElement('afterend', knowl_output)
    }
    defer( function () {
      try
      {
        renderMathInElement(document.getElementById(output_id), katexOpts)
      }
      catch(err) {
        console.log("err:" + err)
      }
    }, 'renderMathInElement')
  }
} //~~ end click handler for *[knowl] elements


/*
 * register a click handler for each element with the knowl attribute
 *  also add a unique ID.
 *  this is necessary when the same reference is used several times. */
var knowl_id_counter = 0
function knowl_handle(evt) {
  console.log("knowl_handle")
  evt.preventDefault()
  var knowl = evt.target || evt.srcElement
  if(!knowl.getAttribute("knowl-uid") ) {
    console.log("knowl-uid = " + knowl_id_counter)
    knowl.setAttribute("knowl-uid", knowl_id_counter)
    knowl_id_counter++
  }
  knowl_click_handler(evt)
}

function knowl_register_onclick(element) {
  console.log("knowl_register_onclick");
  console.log(element.querySelectorAll('*[knowl]'));
  element.querySelectorAll('a[knowl]').forEach(
   (knowl) => {
     console.log(knowl)
     knowl.onclick = debounce(knowl_handle, 500, true)
   }
  )
}

if( document.readyState !== 'loading' ) {
    console.log( 'document is already ready, just execute code here' );
    knowl_register_onclick(document);
} else {
    document.addEventListener('DOMContentLoaded', function () {
        console.log('document was not ready, place code here' );
        knowl_register_onclick(document);
    });
}

console.log("loaded");

