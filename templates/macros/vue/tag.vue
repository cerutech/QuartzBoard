<div class="control">
    <div class="tags has-addons">
	
        <span class="tag is-dark">{{tag.type}}</span>

        <span class="tag is-info" v-if="tag.type == 'fandom'">{{tag.name}}</span>
		
        <span class="tag is-danger" v-if="tag.type == 'character'">{{tag.name}} <span>{{tag.fandom_internal}})</span></span>
		
        <span class="tag is-warning" v-if="tag.type == 'kink'">{{tag.name}}</span>
		<span class="tag is-success" v-if="tag.type == 'author'">{{tag.name}}</span>
    </div>
</div>