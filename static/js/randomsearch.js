function random_text()
{};
var random_text = new random_text();
var number = 0;
random_text[number++] = "france"
random_text[number++] = "staggering genius"
random_text[number++] = "making comics"
random_text[number++] = "free city"
random_text[number++] = "political fictions"
random_text[number++] = "blink"
random_text[number++] = "harry potter"
random_text[number++] = "beautiful evidence"
random_text[number++] = "engineers revolt"
random_text[number++] = "against love"
random_text[number++] = "little women"
random_text[number++] = "tom sawyer adventure"
random_text[number++] = "raintree county"
random_text[number++] = "whole earth catalog"
var random_number = Math.floor(Math.random() * number);
        document.write("<input type='text' name='q' value='");
        document.write(random_text[random_number]);
        document.write("' size='19' title='Type your search terms here.' />");    