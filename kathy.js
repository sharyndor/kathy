sock = null

function addMessage(m) {
  var div = messageBox.appendChild(document.createElement('div'))
  div.appendChild(document.createTextNode(m))
  return div
}

function useLoginBox() {
  while (inputBox.firstChild) {
    inputBox.removeChild(inputBox.firstChild)
  }

  var serverDiv = inputBox.appendChild(document.createElement('div'))
  serverDiv.appendChild(document.createElement('a')).text = 'Server:'
  var serverInput = serverDiv.appendChild(document.createElement('input'))
  serverInput.value = 'localhost:8080'

  var loginDiv = inputBox.appendChild(document.createElement('div'))
  loginDiv.appendChild(document.createElement('a')).text = 'Login:'
  var loginInput = loginDiv.appendChild(document.createElement('input'))
  loginInput.value = 'Foo'

  loginInput.focus()
  loginInput.onkeyup = e => {
    if (e.key == 'Enter' && loginInput.value) {
      sock = new WebSocket('ws://' + serverInput.value)
      sock.onmessage = handleResponse
      sock.onopen = () => {
        sock.send(JSON.stringify({
          type: 'connect',
          sender: loginInput.value
        }))
      }
    }
  }
}

function handleConnect() {
  inputBox.parentElement.removeChild(inputBox)
  chatInput.focus()
}

function handleMessage(response) {
  switch (response.dataType) {
    case 'text': handleTextMessage(response); break;
    case 'content': handleContentMessage(response); break;
  }
}

function handleTextMessage(response) {
  addMessage(`[${response.sender}]: ${response.text}`)
}

function handleContentMessage(response) {
  var message = addMessage(`[${response.sender}]: Click to download`)
  message.contentId = response.id
  message.style.cursor = 'pointer'
  message.onclick = e => {
    sock.send(JSON.stringify({
      type: 'content',
      id: response.id,
    }))
  }
}

function addExpandable(element, initialState) {
  element.expanded = false;
  setSize(element, element.expanded)
  element.style.cursor = 'pointer'
  element.onclick = e => { toggleSize(e.target) }
}

function blob64(data, dataType) {
  var byteChars = atob(data)
  var byteNums = new Array(byteChars.length)
  for (var i = 0; i < byteChars.length; ++i) {
    byteNums[i] = byteChars.charCodeAt(i)
  }
  var bytes = new Uint8Array(byteNums)
  return new Blob([bytes], { type: dataType })
}

function handleContent(response) {
  switch (response.dataType.split('/')[0]) {
    case 'image': handleImage(response); break;
    case 'video': handleVideo(response); break;
  }
}

function handleImage(response) {
  var div = document.createElement('div')

  var img = div.appendChild(document.createElement('img'))
  img.src = window.URL.createObjectURL(blob64(response.data, response.dataType))
  addExpandable(img, false)

  for (var message of messageBox.children) {
    if ('contentId' in message && message.contentId == response.id) {
      messageBox.replaceChild(div, message);
    }
  }
}

function handleVideo(response) {
  var div = document.createElement('div')

  var video = div.appendChild(document.createElement('video'))
  video.setAttribute('controls', '')
  video.setAttribute('width', '50%')

  var source = video.appendChild(document.createElement('source'))
  source.src = window.URL.createObjectURL(blob64(response.data, response.dataType))
  source.type = response.dataType

  for (var message of messageBox.children) {
    if ('contentId' in message && message.contentId == response.id) {
      messageBox.replaceChild(div, message);
    }
  }
}

function handleResponse(response) {
  var data = JSON.parse(response.data)
  switch (data.type) {
    case 'connect': handleConnect(data); break;
    case 'message': handleMessage(data); break;
    case 'content': handleContent(data); break;
  }
}

init = false

chatInput.value = ""
chatInput.onkeyup = e => {
  if (e.key == 'Enter') {
    sock.send(JSON.stringify({
      type: 'message',
      dataType: 'text',
      text: chatInput.value,
    }))

    chatInput.value = ""
  }
}

chatInput.ondrop = e => {
  e.preventDefault()
  for (var item of e.dataTransfer.items) {
    if (item.kind == 'file') {
      file = item.getAsFile()
      id = Math.floor(Math.random() * 100000)
      reader = new FileReader()
      reader.onload = () => {
        sock.send(JSON.stringify({
          id: id,
          type: 'message',
          dataType: 'content'
        }))

        sock.send(JSON.stringify({
          type: 'content',
          id: id,
          data: reader.result.split(',')[1],
          dataType: file.type,
        }))
      }
      reader.readAsDataURL(file)
    }
  }
}

useLoginBox()

function setSize(element, expanded) {
  if (expanded) {
    element.style.maxWidth = '100%'
    element.style.maxHeight = '100%'
  } else {
    element.style.maxWidth = '20vw'
    element.style.maxHeight = '20vh'
  }
}

function toggleSize(element) {
  element.expanded = !element.expanded
  setSize(element, element.expanded)
}
