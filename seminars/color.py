class StandardColors(object):
    white = 'white'
    black = 'black'
    purple = 'purple'

    # Reds
    red = 'red'
    col_light_red_1 = '#fdd'
    col_light_red_2 = '#fee'

    # Blues
    blue = 'blue'
    lightblue = 'lightblue'
    steel_blue = '#3c769d'
    blue_2 = '#336699'
    hyperlink_blue = '#0000cc'

    # Greys
    blue_grey = '#b0bed9'
    blue_grey_1 = '#9fafd1'
    red_grey = '#a19b9e'
    light_red_grey = '#d1cfd0'
    grey = '#999'
    dark_grey = '#333'
    dark_grey_1 = '#666'
    # I think we need all the un-commented light_grey
    light_grey_1 = '#eee'
    light_grey_2 = '#cdcdcd'
    light_grey_3 = '#ddd'
    light_grey_4 = '#ccc'
    #light_grey_5 = '#c4c4c4'
    #light_grey_6 = '#d1d1d1'
    #light_grey_7 = '#d5d5d5'
    #light_grey_8 = '#e2e2e2'
    light_grey_9 = '#e9e9e9'
    almost_white = '#fafbfa'

    orange_1 = '#ff9900'

    def __contains__(self, color):
        return color in self.__class__.__dict__
    def __getitem__(self, color):
        return self.__class__.__dict__[color]
    def __iter__(self):
        return iter(self.__class__.__dict__)

c = StandardColors()

class ColorScheme(object):
    colors = {
        'col_main_d':  None, # Header and footer
        'col_main_dl': None, # Header and footer text
        'col_a_knowl': '#292', # Links
        'col_main': None,      # Links
        'col_link': '#2a2',    # Links
        'col_visited': 'col_main',       # Visited links in body
        'col_body_text': 'col_main', # Links in body
        'col_sidebar_text': 'col_main', # Sidebar text in body and header, under Dat, gets over-written for the rest.
        'col_sidebar_links': 'col_main', # Sidebar link text
        'col_sidebar_header_links': 'col_main', # Sidebar header links
        #'col_search_border': 'col_main',
        'col_main_2': None, # Main link hovers
        'col_main_l': None, # Tabs
        'col_main_b': 'col_main_l', # Buttons -- not defined in non-original color schemes
        'col_main_lg': None, # Shadow and bottom border
        'col_main_ld': None, # Box background
        'col_main_ll': None, # Beta text
        'col_main_g': '#474',

        # Body colors
        'body_background': c.white,
        'body_text': c.black,
        'box_table_text': c.black,

        # Knowl colors
        'knowl_error': c.purple,
        'knowl_border': '#ddf',
        'knowl_header_background': 'col_main_ld',
        'knowl_hover': 'knowl_border',
        'knowl_background': '#eef',
        'knowl_hyper_text': '#006',
        'knowl_title_text': '#004',
        'knowl_underline': '#aaf',
        'knowl_hover_text': '#88f', # Text color when hovering on link in header/footer
        'knowl_thin_border': '#88f', # Darker border at base of top knowl bar
        'knowl_shadow': '#88b',
        'knowl_1': '#99b3ff', # paging_full_numbers span.paginate_button
        'knowl_db': '#66d', # knowl-qm.active
        'knowl_border_links': 'knowl_hyper_text',
        'knowl_border_hover': 'knowl_hyper_text',
        'knowl_border_text' : c.grey,
        # td.sorting
        'knowl_ld_1': '#c4c4ff',
        'knowl_l_1': '#D3D6FF',
        'knowl_l_2': '#DADCFF',
        'knowl_l_3': '#E0E2FF',
        'knowl_l_4': '#EAEBFF',
        'knowl_l_5': '#F2F3FF',
        'knowl_l_6': '#F9F9FF',
        'knowl_l_7': '#d1d1ff',
        'knowl_l_8': '#d5d5ff',
        'knowl_l_9': '#eef',

        # Content colors
        'content_text': c.black, # Body section text TODO: change
        'content_text_h3': 'col_main', # TODO: where is this used?
        'content_border': 'col_main', # TODO: where is this used?
        'content_background': 'col_main_ll',
        'content_border_red': c.red,
        'content_background_red': c.col_light_red_1,

        # contributors, i.e., contribs
        'contrib_border': 'col_main_ld',
        'contrib_background': 'col_main_ld',
        'contrib_text_affil': c.dark_grey,
        'contrib_text_notes': c.dark_grey_1,

        # footer colors
        'footer_background': 'col_main_ld',
        'footer_border': 'col_main_lg',
        'footer_text': 'col_main_dl',

        # a colors
        'a_text': 'col_body_text', # This occurs in for some hyperlinks, and sidebar header text.
        'a_inactive': c.black,
        'a_text_visited': 'col_visited', # This occurs for the rest of the hyperlinks, and sidebar header text, i.e., once visited
        'a_text_hover': c.black,
        'a_background_hover': 'col_main_l',

        'a_nav_text': c.white,
        'a_nav_background': 'col_main',
        'a_nav_border': c.white,

        # hr': 'horizontal rule
        'hr_border': 'col_main_l',

        # Upper right hand corner searchbox, which has been disabled
        # 'search_border': 'col_search_border',
        # 'search_background': 'col_main_ld',
        # # Search
        # 'search_background': c.white,
        # 'serach_border': c.white,
        # 'gsa_inactive': 'light_grey_9',
        # 'gsa_active': 'orange_1',
        # 'gs_text_webResult': 'black',
        # 'gs_text': 'col_main',
        # 'gs_border': 'blue_2',



        # Header colors
        'header_background': 'col_main_ld', #Color of the banner at the top
        'header_shadow': 'col_main_lg',
        'header_text_title': 'col_main_d',
        'header_text_topright': 'col_main_dl',
        # Header navi colors
        'header_navi_text': 'col_main_dl',
        'bread_links': 'col_main_dl',

        # flashes
        'flashes_border': c.col_light_red_1,
        'flashes_background': c.col_light_red_2,


        # Properties: the right hand side boxes.
        'properties_border': 'col_main_g',
        'properties_text_h1h2': 'col_main_l',
        'properties_body_background': 'col_main_ll',
        'properties_header_text': 'col_main_d',
        'properties_header_background': 'col_main_l',
        'properties_collapser': 'col_main_d', #The little circle-arrow thingy


        # Sidebar: left hand side sidebar.
        'sidebar_background': 'col_main_ll',
        'sidebar_background_h2': 'col_main_l', #sidebar tab background
        'sidebar_text': c.black, #sidebar non-header non-link non-future text
        'sidebar_text_h2': c.black, # non-link sidebar header text.
        'sidebar_h2_hover': 'sidebar_text_h2', # sidebar tab hover text color

        'sidebar_background_hover': 'col_main_l',
        'sidebar_background_li': 'col_main_ll',
        'sidebar_background_h2_hover': 'col_main_2',
        'sidebar_bkg_highlight': 'col_main_l',
        'sidebar_bkg_highlight_knowl': 'knowl_db', # This was broken: col_knowl_d
        'sidebar_text_future': c.grey,
        'sidebar_text_beta': c.purple,
        'sidebar_background_off': c.white,


        # Buttons
        'button_background': 'col_main_b',
        'select_background': 'col_main_ll',
        'button_border': 'col_main_lg',
        'button_background_hover': 'col_main_l',
        'button_border_hover': 'col_main_lg',
        'button_background_inactive': 'light_grey_1',
        'button_border_inactive': 'col_light_red_1',
        'input_border': 'col_main_lg',


        # Tables
        'table_background_hover': 'col_main_l',
        'table_ntdata_background': 'col_main_2',
        'table_ntdata_background_2': 'col_main_ll',
        'table_ntdata_background_c1': c.white, # tr:first-child, odd
        'table_ntdata_background_cn': 'col_main_ll', #tr:nth-child, even
        'table_ntdata_border': 'col_main_lg',
        'table_ntdata_border_bottom': c.grey,

        #index-boxes todo
        'box_background': c.white,
        'box_background_img': 'col_main_ll',
        'box_background_title': 'col_main_l',

        #Maass nav and show
        'maas_table_bkg': c.white,
        'maas_table_bkg_hl': 'col_main_l',
        'maas_coff_bkg': c.white,

        # Chi tables
        'chitable_imprimitive': c.blue,
        'chitable_primitive': 'col_main',
        'chi_background': 'col_main_2',
        'chi_table_background_off': c.white,
        'chi_border': 'col_main_lg',
        'chi_table_background': 'col_main_ld', # This was specified twice in color.css; could also be col_main_ll
        'chi_table_border': 'col_main_dl',

        # acknowledgements
        'text_affil': '#333',
        'text_notes': '#555',
        'text_trad_hyperlink': c.black,

        # Elliptic curve colors
        'ec_background': 'col_main_2',

        # Siegel modular forms
        'smf_background': 'col_main_ll',
        'smf_border': 'col_main_lg',

        # L-functions
        'lf_an_button_bkg': 'col_main_ld',
        'lf_an_button_brd': 'col_main_lg',
        'lf_ar_button_bkg': c.light_grey_1,
        'lf_ar_button_brd': c.col_light_red_1,
    }
    def dict(self):
        def get(key):
            val = getattr(self, key, None)
            if val is not None:
                return val
            default = self.colors.get(key)
            if default is not None:
                if default.startswith('#'):
                    return default
                elif default in c:
                    return c[default]
                elif default in self.colors:
                    return get(default)
                else:
                    raise ValueError("Unrecognized color %s"%default)
            raise ValueError("No value for %s specified"%key)
        scheme = {}
        for std_color in c:
            val = getattr(self, std_color, None)
            if val is None:
                val = c[std_color]
            scheme[std_color] = val
        for key in self.colors:
            scheme[key] = get(key)
        return scheme

    @classmethod
    def __allsubclasses__(cls):
        # Recursive version of __subclasses__ where subclasses are marked as leaves if they have a code attribute
        for subcls in cls.__subclasses__():
            if hasattr(subcls, 'code'):
                yield subcls
            else:
                for subsub in subcls.__allsubclasses__():
                    yield subsub

class GreyKnowls(ColorScheme):
    # Subclasses need to set knowl_hyper_text and knowl_shadow
    knowl_border = '#CDCDCD'
    knowl_background = '#F5F5F5'
    knowl_title_text = c.black
    knowl_hover_text = c.black
    knowl_thin_border = '#CDCDCD'
    body_background = c.white
    def __init__(self):
        self.knowl_underline = self.knowl_hyper_text

class SteelBlue(GreyKnowls):
    code = 19
    col_main_ld = '#90CAF9'
    col_main_dl = c.black
    col_a_knowl = '#1C61A6'
    col_main    = '#1565C0' # P1-800
    col_link    = '#1C61A6'
    col_visited = '#1C61A6'
    col_body_text = '#1565C0' # P1-800
    col_sidebar_text = c.black
    col_sidebar_links = '#1565C0' # P1-800
    col_sidebar_header_links = '#0D47A1' # P1-900
    #col_search_border = '#0D47A1' # P1-900
    col_main_2  = '#EEEEEE'
    col_main_l  = '#90CAF9' # P1-200
    col_main_lg = '#0D47A1' # P1-900
    col_main_ll = '#E3F2FD' # P1-50
    col_main_d  = c.black # ?00
    knowl_hyper_text = '#1565C0' # P1-800
    knowl_shadow = '#0D47A1' # P1-900
    sidebar_background_hover = c.white # '#CCE6FC' # accessibility change
    a_background_hover = '#E3F2FD' # accessibility change
    # knowl_hover = '#FFF8C1' # yellow, lighter than knowl border
    knowl_hover = '#EDEDED'
    knowl_border_links = c.black
    knowl_border_hover = c.black
    sidebar_h2_hover = c.white
    sidebar_background_h2_hover = '#0D47A1'
    knowl_border_text = '#333'
    sidebar_text_beta = '#006d05'
    knowl_error = '#006d05'
    chi_table_background = '#E3F2FD'
    chitable_imprimitive = c.black
    table_ntdata_background = c.white

class Slate(SteelBlue):
    col_main_ld = "#373737"  # header background\
    header_shadow = 'white'  # remove shadow by making it white
    footer_border = "#f8d047"  # yellow from logo, border along footer
    header_text_title = 'white'
    col_main_dl = 'white'
    button_background = "#0066dd"
    button_border = "#0033bb"
    col_visited = "#00499b"
    # col_main = '#373737'
    a_text = "#373737"  # h2 headers
    col_link = "#0033bb"  # links
    col_visited = "#0033bb"  # visited links
    col_main_lg = "#373737"  # text box border
    col_main_l = "#aaaaaa"  # button background
    a_background_hover = "#e0e0e0"
    table_background_hover = "#e0e0e0"
    knowl_background = "#fffaed"

