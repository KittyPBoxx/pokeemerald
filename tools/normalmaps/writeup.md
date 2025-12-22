
# Directional Lighting effects.

Directional ligthing effects can be quite expensive so simulating them in older games often requires work arounds. 
In the alpha blended normal maps we went over how the blend register can be used for effects like the orbs glowing and lighting effects in maps. 
However this bakes the effects into the maps and isn't much different from the baked in shadows that most buildings use already. 
If you are new to GBA graphics I recommend reading that first for some background. 

This branch covers directional shadows and frame blended normal maps for sprites. 
<link>

<video>

# Light Sources 

- Cover event objects as light sources
- Tile Range
- Light Color 


# Directional Shadow 

- Borrowing the refelection field effect
- Every shadow palette can be shared
- Sprite limits
- OAM transform per shadown. OAM limits 32 sprites. But actually less because the player will need one
- Shadow Priority

# Normal Mapping

- What are normal maps, image of a cone 
- Code for updating the normal palettes every frame


# Normal Map Generation tool

- Programatic generation of noraml maps, 3d model, manually painting, netural net approches, shape approches, sobel filters.
- value vs lightness, soble, outline boosting, curves and blur. The normal mapping tool. 
- Short commings with flat colors. e.g. picachu ears  
- SDF

# Quantizing normal maps

At a minimum retro palettes need 4 colors for directions. But if we tried to do it all with one sprite we'd only have 4 colors for our sprites 
We're uing 4bpp sprites in the overworld that means we our normal map will have one color mapped to transpatrent and we can allocate 15 different colors for directions. 
Instead we need to blend 2 layers togther this allows up to have 15 different directions for every single color on the sprite. 
i.e we can represent an pixel as facing 1 of 15 directions and light it accordingly dedending on the direction light source

This is very cheap compared to regular lighting techniques, two static images are rendered over each other, then all we have to do each frame is update 15 palette slot colors. 
However as discussed before this does not allow sprites to blend with sprites which means we'd have to use a backgroudn layer. 
To make matters worse we can't more tiles individually on the background layers, only offset the layers as a whole which means that you'd only be able to light the player with this technique as other events 
need to move independently. 

There's work around that would allow us to work with every sprite at the same time and not even use any additional palette slots but this requires using one of the more cursed GBA techniques. 


# Frame blending

Frame blending is a technique used in several gba games including first party games like zelda and fzero. The technique alloes doesn't use the blend register and allow very limited alpha blending, anit liasing, and motion blur. 

However it's not somthing officially supported by gba hardware and it's kind of a quirk of the screen that it works rather than an intended feature. 
This is because the refresh rate of the screen (the number of times it can recieve updates per second) 59.97hz (16.7ms) is faster than the response time is slower than the response time (the time it takes for an update to fully show)
because the older technology means the pixels take time to physically change colour.

There are a few weird effects you can get on GBA screens that arn't part of the specification, what makes frame blending different is that lots of popular games made use of it to some extent.
This means its not only supported on official hardware (GBA, DS, 3DS, Gameboy player (in GCI software)) it also gets supported to some extend on most emulators and new screen mods. 
However, the effect is emulated pretty inconsistently and the defauly behaviour of emulators is often to switch it off as this makes a sharper more responsive image.  

Because this isn't part of the devices accuracy, some normally accurate emulators like NanoBoyAdvance don't handle the frame blending well even though they have a setting for it. That said MGBA (with open gl rendering), and VBA-M produce a reasonable result.

# LCD Screens (why it works)

If you're happy just to accept that alternating an image every frame results in a blended image you can skip this section. 
If not I'll attempt to explain more of what's going on here. 

Let's forget that the screen has different colors and imagine it's just 1 big black or white pixel. 
The GBA uses a TFT LCD display. Here's a very simplified diagram:

```
              Polarizer (vertical)  Polarizer (horizontal)
(︶︹︺)           | | | | |              — — — — —
NO LIGHT          | | | | |  <<<<<<<<    — — — — —  <<<<<<<<  <---- LIGHT
                  | | | | |              — — — — —

```

When light passes through a vertical polarizer all horizontal light is blocked.
When light passes through a horizontal polarizer all vertical light is blocked.
So with a horizontal and vertical polarizer all light becomes blocked.

The natural state twisted state of the crystal fluid twists the light, 
so by putting a liquid crystal layer between the polarizers it twists the light allowing it to pass through and getting us back to where we started.

```
                 Polarizer (vertical)    Liquid Crystal (OFF)     Polarizer (horizontal)
(o^▽^o)             | | | | |                x x x x x                — — — — —
LIGHT      <<<<<<<<  | | | | |   <<<<<<<<     x x x x x  <<<<<<<<      — — — — —  <<<<<<<<   <---- LIGHT
MADE IT!             | | | | |                x x x x x                — — — — —
        
```

However, when a voltage is applied the crystals rotate, no longer twisting the light, so it gets blocked 

```
                 Polarizer (vertical)    Liquid Crystal (ON)     Polarizer (horizontal)
凸(￣ヘ￣)            | | | | |               ~ ~ ~ ~ ~                — — — — —
NO LIGHT             | | | | |   <<<<<<<<    ~ ~ ~ ~ ~    <<<<<<<<    — — — — —   <<<<<<<<   <---- LIGHT
                     | | | | |               ~ ~ ~ ~ ~                — — — — —

```


As you can see, even if the controller can switch to a different voltage at 59.7 times a second, if the crystals can't twist or return to their original state fast enough then some of the old image will still be present in the next frame. 
It's worth noting it's not exactly a 50/50 blend of the two images, because returning the the twisted state (i.e becomming lighter) is slower than untwisting (i.e becomming darker). 

Traditionally TFT screens are normally know for having good response times, but GBA screens were cheap, old and low power so there are a few ways they're worse than modern displays. 
- Liquid crystal viscosity. This means its slower for the crystals to turn.
- Plate distance. The voltage is applied to the liquid between two plated, the closer they are together the faster the refresh.
- Power consuming techniques like overdrive (applying a higher initial voltage, then tapering off for faster change) were not used. 


# Frame Blending approaches and flicker reduction

- On off
- Priority
- Pattern inversion
- Animation